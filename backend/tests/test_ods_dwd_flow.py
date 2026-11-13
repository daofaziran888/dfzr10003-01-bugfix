"""接入流水 → 明细清洗链路回归测试。

覆盖：
- 导出入口返回全量流水且为可下载文件（修复 /export 被整数路径参数截获的 422）
- 暂停接入真实生效，列表/导出/清洗准入读取同一份状态
- 状态只能按 草稿→运行中→已暂停→已完成 单向推进，禁止跳级与回退
- 同一启动/暂停请求重复提交幂等；暂停后再启动从分区水位续跑，不重开已完成批次
- 版本冲突走乐观锁；冲突时以最近一次通过校验并成功写入的记录为准
- ODS-0001 草稿、ODS-0003 已暂停回归；导出每条流水与清洗页准入结论一致
- 已归档流水不再出现在待清洗队列
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def test_export_is_downloadable_file_with_all_entries(client: TestClient) -> None:
    response = client.get("/api/ods/export")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]
    # 去掉 BOM 后按 CSV 文本核对：种子里三条流水全部出现在导出中
    text = response.content.decode("utf-8").lstrip("\ufeff")
    for code in ("ODS-0001", "ODS-0002", "ODS-0003"):
        assert code in text
    assert "准入结论" in text  # 导出与列表/清洗页使用同一状态结论字段


def test_pause_takes_effect_and_dwd_uses_same_status(client: TestClient) -> None:
    response = client.post("/api/ods/2/actions", json={"action": "暂停接入"})
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["entry"]["status"] == "已暂停"

    detail = client.get("/api/ods/2").json()
    assert detail["status"] == "已暂停"

    dwd = {row["流水编号"]: row for row in client.get("/api/dwd").json()["items"]}
    assert dwd["ODS-0002"]["接入状态"] == "已暂停"
    assert dwd["ODS-0002"]["可准入"] == "否"


def test_flat_request_body_is_accepted(client: TestClient) -> None:
    # 前端历史发送的就是扁平 {"action": ...}，旧模型会解析成空动作
    response = client.post("/api/ods/2/actions", json={"action": "暂停接入"})
    assert response.json()["entry"]["status"] == "已暂停"


def test_status_moves_forward_only(client: TestClient) -> None:
    # 草稿禁止跳级到暂停/完成/归档
    for action in ("暂停接入", "完成接入", "归档流水"):
        result = client.post("/api/ods/1/actions", json={"action": action}).json()
        assert result["ok"] is False
        assert client.get("/api/ods/1").json()["status"] == "草稿"

    # 运行中禁止回退式重复启动之外的跳级：先启动再直接归档
    client.post("/api/ods/1/actions", json={"action": "启动接入"})
    result = client.post("/api/ods/1/actions", json={"action": "归档流水"}).json()
    assert result["ok"] is False
    assert client.get("/api/ods/1").json()["status"] == "运行中"

    # 合法单向走通：运行中 → 已暂停 → 运行中（续跑）→ 已完成
    assert client.post("/api/ods/1/actions", json={"action": "暂停接入"}).json()["entry"]["status"] == "已暂停"
    resumed = client.post("/api/ods/1/actions", json={"action": "启动接入"}).json()["entry"]
    assert resumed["status"] == "运行中"
    assert client.post("/api/ods/1/actions", json={"action": "完成接入"}).json()["entry"]["status"] == "已完成"


def test_start_is_idempotent_and_resumes_from_watermark(client: TestClient) -> None:
    # 首次启动
    first = client.post("/api/ods/1/actions", json={"action": "启动接入"}).json()["entry"]
    assert first["status"] == "运行中"
    version_after_start = first["version"]
    active_batch = first["active_batch"]

    # 重复启动：幂等，不产生写入
    duplicate = client.post("/api/ods/1/actions", json={"action": "启动接入"}).json()
    assert duplicate["ok"] is True
    assert duplicate["entry"]["version"] == version_after_start
    assert duplicate["entry"]["active_batch"] == active_batch

    # 暂停关闭当前批次并记录水位
    paused = client.post("/api/ods/1/actions", json={"action": "暂停接入"}).json()["entry"]
    assert paused["partition_watermark"] == active_batch
    assert active_batch in paused["completed_batches"]

    # 再启动：新批次必须晚于水位，已完成批次不允许重新打开
    resumed = client.post("/api/ods/1/actions", json={"action": "启动接入"}).json()["entry"]
    assert resumed["active_batch"] != active_batch
    assert resumed["active_batch"] not in resumed["completed_batches"]
    assert active_batch in resumed["completed_batches"]
    assert resumed["active_batch"] > paused["partition_watermark"]


def test_pause_is_idempotent(client: TestClient) -> None:
    client.post("/api/ods/2/actions", json={"action": "暂停接入"})
    version = client.get("/api/ods/2").json()["version"]
    duplicate = client.post("/api/ods/2/actions", json={"action": "暂停接入"}).json()
    assert duplicate["ok"] is True
    assert duplicate["entry"]["version"] == version
    assert duplicate["entry"]["status"] == "已暂停"


def test_optimistic_version_conflict_rejected(client: TestClient) -> None:
    # ODS-0002 初始版本为 1，先暂停一次推进到新版本
    client.post("/api/ods/2/actions", json={"action": "暂停接入"})
    current = client.get("/api/ods/2").json()
    stale_version = current["version"] - 1
    assert stale_version == 1

    conflict = client.post(
        "/api/ods/2/actions",
        json={"action": "启动接入", "expected_version": stale_version},
    )
    assert conflict.status_code == 409
    # 被拒后状态不变，仍以最近一次成功写入且通过校验的记录（已暂停）为准
    assert client.get("/api/ods/2").json()["status"] == "已暂停"

    # 携带当前版本可正常提交
    ok = client.post(
        "/api/ods/2/actions",
        json={"action": "启动接入", "expected_version": current["version"]},
    )
    assert ok.status_code == 200
    assert ok.json()["entry"]["status"] == "运行中"


def test_regression_ods_0001_draft_and_ods_0003_paused(client: TestClient) -> None:
    ods = {row["流水编号"]: row for row in client.get("/api/ods").json()["items"]}
    assert ods["ODS-0001"]["status"] == "草稿"
    assert ods["ODS-0003"]["status"] == "已暂停"

    # 导出中的每条流水与清洗页当次可见的准入结论相同
    export_text = client.get("/api/ods/export").content.decode("utf-8").lstrip("\ufeff")
    dwd = {row["流水编号"]: row for row in client.get("/api/dwd").json()["items"]}
    for code, row in ods.items():
        assert f"{code}," in export_text
        assert row["准入结论"] == dwd[code]["准入结论"]
        assert row["可准入"] == dwd[code]["可准入"]

    # 草稿与已暂停均不可准入
    assert dwd["ODS-0001"]["可准入"] == "否"
    assert dwd["ODS-0003"]["可准入"] == "否"


def test_archived_entry_leaves_pending_queue_but_kept_in_export(client: TestClient) -> None:
    # ODS-0003 已是暂停态，满足归档前置条件
    archived = client.post("/api/ods/3/actions", json={"action": "归档流水"}).json()
    assert archived["ok"] is True
    assert archived["entry"]["archived"] is True

    queue_ids = [row["id"] for row in client.get("/api/dwd").json()["items"]]
    assert 3 not in queue_ids
    assert client.get("/api/dwd/3").status_code == 404

    # 已归档流水仍在接入清单与导出中可追溯，但结论是离开待清洗队列
    ods_detail = client.get("/api/ods/3").json()
    assert ods_detail["可准入"] == "否"
    assert "归档" in ods_detail["准入结论"]
    export_text = client.get("/api/ods/export").content.decode("utf-8").lstrip("\ufeff")
    assert "ODS-0003" in export_text


def test_dwd_export_matches_visible_admission(client: TestClient) -> None:
    visible = client.get("/api/dwd").json()["items"]
    export_text = client.get("/api/dwd/export").content.decode("utf-8").lstrip("\ufeff")
    for row in visible:
        assert row["流水编号"] in export_text
        assert row["准入结论"] in export_text


def test_unknown_action_rejected(client: TestClient) -> None:
    result = client.post("/api/ods/1/actions", json={"action": "删除接入"}).json()
    assert result["ok"] is False
    assert client.get("/api/ods/1").json()["status"] == "草稿"
