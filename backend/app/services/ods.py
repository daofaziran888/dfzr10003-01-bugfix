"""贴源层接入业务规则：接入流水的登记、筛选与动作都委托给共享状态引擎。

列表、导出、动作、明细清洗准入口径全部来自 :mod:`app.services.flow_state`，
保证两个页面读到的是同一份合法状态结论。
"""
from __future__ import annotations

from typing import Any

from app.services import flow_state
from app.store import store

MODULE = "ods"
REQUIRED_FIELDS = ["流水编号", "来源系统", "源表名称"]
STATUS_ORDER = list(flow_state.FLOW_STATUSES)


class OdsService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = flow_state.ods_rows()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("流水编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = [flow_state.enrich_entry(row) for row in rows[start:start + size]]
        return page_rows, total

    def list_all_for_export(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        """导出与列表共用同一筛选口径和同一份状态，仅去掉分页。"""
        rows = flow_state.ods_rows()
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("流水编号", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [flow_state.enrich_entry(row) for row in rows]

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = flow_state.find_ods_entry(entry_id)
        return flow_state.enrich_entry(entry) if entry else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        # 登记环节允许补充落地表等选填信息
        for optional in ("落地表名", "接入周期", "分区粒度", "保留天数", "最近接入时间"):
            if values.get(optional) is not None:
                entry[optional] = values.get(optional)
        entry["status"] = STATUS_ORDER[0]
        rows.append(entry)
        return flow_state.enrich_entry(flow_state.normalize_entry(entry)), []

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        expected_version: int | None = None,
    ) -> tuple[dict[str, Any] | None, str, int | None]:
        """返回 (流水, 说明, 冲突错误码)。冲突错误码：None 正常，409 版本冲突。"""
        entry = flow_state.find_ods_entry(entry_id)
        if entry is None:
            return None, f"接入流水 {entry_id} 不存在", None
        try:
            updated, message = flow_state.advance(
                entry, action, expected_version=expected_version
            )
        except flow_state.IllegalTransitionError as exc:
            return None, str(exc), None
        except flow_state.ConflictError:
            return None, "状态记录冲突：该流水已被其他请求更新，请刷新后重试", 409
        return flow_state.enrich_entry(updated), message, None
