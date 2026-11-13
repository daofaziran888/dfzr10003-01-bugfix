"""接入流水状态引擎：状态机、分区水位、幂等与冲突处理的唯一权威实现。

列表、导出、明细清洗准入三个入口都通过本模块读取同一份状态结论，避免各处
自行解释状态导致口径不一致。

冲突处理策略（最后成功写入胜出 + 乐观版本号）：
- 每条流水带单调递增的 ``version``，仅在通过校验且真正落盘的写入后 +1；
- 写操作在进程内互斥锁内完成「读取-校验-写入」，并发请求串行化；
- 请求方可携带 ``expected_version``，版本过期直接拒绝；不携带时，
  以最近一次通过校验并成功写入的记录为准（last-write-wins among validated writes）。
"""
from __future__ import annotations

import threading
from datetime import date, datetime, timedelta
from typing import Any

from app.store import store

ODS_MODULE = "ods"

# 接入流水只允许在四个状态间单向推进
FLOW_STATUSES: tuple[str, ...] = ("草稿", "运行中", "已暂停", "已完成")

# 动作 -> (合法前置状态, 目标状态)。只列真正推动状态前进的流转。
LEGAL_TRANSITIONS: dict[tuple[str, str], str] = {
    ("草稿", "启动接入"): "运行中",
    ("运行中", "暂停接入"): "已暂停",
    ("已暂停", "启动接入"): "运行中",
    ("运行中", "完成接入"): "已完成",
}

# 重复提交同一启动/暂停请求时幂等：不报错、不写入、版本号不变。
IDEMPOTENT_ACTIONS: dict[tuple[str, str], str] = {
    ("运行中", "启动接入"): "接入已在运行中，重复启动请求已忽略",
    ("已暂停", "暂停接入"): "接入已暂停，重复暂停请求已忽略",
}

# 归档不是状态回退，只允许在非运行态打归档标记
ARCHIVE_ALLOWED_STATUSES: tuple[str, ...] = ("已暂停", "已完成")
ARCHIVE_ACTION = "归档流水"
ALL_ACTIONS = ("启动接入", "暂停接入", "完成接入", ARCHIVE_ACTION)

# 各状态下页面可呈现的合法动作
NEXT_ACTIONS: dict[str, tuple[str, ...]] = {
    "草稿": ("启动接入",),
    "运行中": ("暂停接入", "完成接入"),
    "已暂停": ("启动接入", "归档流水"),
    "已完成": ("归档流水",),
}

_write_lock = threading.RLock()


class ConflictError(Exception):
    """携带过期版本号的写入与最新记录冲突。"""


class IllegalTransitionError(Exception):
    """动作不符合单向状态机要求（跳级或回退）。"""


def _today_iso() -> str:
    return date.today().isoformat()


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _next_partition(partition: str) -> str:
    """分区按天推进；解析失败时退化为当天，保证不抛异常中断接入。"""
    try:
        return (date.fromisoformat(partition) + timedelta(days=1)).isoformat()
    except ValueError:
        return _today_iso()


def normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """给历史/种子流水补齐水位、批次、版本等字段，原地修改后返回。"""
    status = entry.get("status")
    if status not in FLOW_STATUSES:
        status = FLOW_STATUSES[0]
        entry["status"] = status
    base_partition = str(entry.get("最近接入时间") or _today_iso())
    entry.setdefault("archived", False)
    entry.setdefault("version", 1)
    entry.setdefault("updated_at", _now_iso())
    entry.setdefault("partition_watermark", None)
    entry.setdefault("completed_batches", [])
    entry.setdefault("active_batch", base_partition if status == "运行中" else None)
    if status == "已暂停" and not entry["completed_batches"]:
        # 暂停态意味着至少有一个分区已经落地关闭
        entry["completed_batches"] = [base_partition]
        entry["partition_watermark"] = base_partition
    if status == "已完成" and not entry["completed_batches"]:
        entry["completed_batches"] = [base_partition]
        entry["partition_watermark"] = base_partition
    entry["pending"] = not entry["archived"] and status != "已完成"
    return entry


def admission_conclusion(entry: dict[str, Any]) -> tuple[bool, str]:
    """接入流水到明细清洗的唯一准入口径，列表/导出/清洗页共用。

    返回 (是否可准入, 结论说明)。已归档流水永远离开待清洗队列。
    """
    if entry.get("archived"):
        return False, "流水已归档，不再进入待清洗队列"
    status = entry.get("status")
    if status == "运行中":
        return True, "接入运行中，可作为明细清洗输入"
    if status == "已完成":
        return True, "接入已完成，分区数据齐备可执行清洗"
    if status == "草稿":
        return False, "接入尚未启动，数据未落地，暂不准入"
    if status == "已暂停":
        return False, "接入已暂停，暂停期间不进入待清洗队列"
    return False, f"接入状态「{status}」不在合法状态序列内，暂不准入"


def enrich_entry(entry: dict[str, Any]) -> dict[str, Any]:
    """在流水副本上附带准入结论，供 ODS 列表/导出与 DWD 队列复用。"""
    enriched = dict(entry)
    admitted, reason = admission_conclusion(entry)
    enriched["可准入"] = "是" if admitted else "否"
    enriched["准入结论"] = reason
    enriched["归档标记"] = "是" if entry.get("archived") else "否"
    return enriched


def _open_next_batch(entry: dict[str, Any], *, resuming: bool) -> None:
    """启动/恢复接入时打开下一个批次，绝不重开已完成批次。"""
    completed = list(entry.get("completed_batches") or [])
    watermark = entry.get("partition_watermark")
    if resuming:
        # 从已记录的分区水位继续：水位之后的下一个分区才是新批次
        next_batch = _next_partition(watermark) if watermark else str(
            entry.get("最近接入时间") or _today_iso()
        )
    else:
        next_batch = str(entry.get("最近接入时间") or _today_iso())
    if next_batch in completed:
        # 水位记录异常时也不允许把已完成批次重新打开
        next_batch = _next_partition(next_batch)
    entry["active_batch"] = next_batch


def _close_active_batch(entry: dict[str, Any]) -> None:
    """暂停/完成时关闭当前批次并推进分区水位。"""
    active = entry.get("active_batch")
    completed = list(entry.get("completed_batches") or [])
    if active and active not in completed:
        completed.append(active)
        entry["partition_watermark"] = active
    entry["completed_batches"] = completed
    entry["active_batch"] = None


def _commit(entry: dict[str, Any]) -> None:
    entry["version"] = int(entry.get("version", 1)) + 1
    entry["updated_at"] = _now_iso()
    entry["pending"] = not entry.get("archived") and entry["status"] != "已完成"


def advance(
    entry: dict[str, Any],
    action: str,
    *,
    expected_version: int | None = None,
) -> tuple[dict[str, Any], str]:
    """对一条流水执行动作，返回 (最新流水, 说明)。

    非法流转抛 :class:`IllegalTransitionError`；版本冲突抛 :class:`ConflictError`。
    幂等请求不产生写入，version 保持不变。
    """
    action = (action or "").strip()
    if action not in ALL_ACTIONS:
        raise IllegalTransitionError(f"动作「{action}」不属于接入流水可执行范围")

    with _write_lock:
        current_version = int(entry.get("version", 1))
        if expected_version is not None and expected_version != current_version:
            raise ConflictError(
                f"状态记录已变更（当前版本 {current_version}，提交基于版本 {expected_version}），"
                "请刷新后以最新记录重试"
            )

        if action == ARCHIVE_ACTION:
            if entry.get("archived"):
                return entry, "流水已归档，重复归档请求已忽略"
            if entry.get("status") not in ARCHIVE_ALLOWED_STATUSES:
                raise IllegalTransitionError(
                    f"当前状态「{entry.get('status')}」不允许归档，仅已暂停或已完成的流水可归档"
                )
            entry["archived"] = True
            entry["active_batch"] = None
            _commit(entry)
            return entry, "接入流水已归档，已移出待清洗队列"

        status = entry.get("status")
        if (status, action) in IDEMPOTENT_ACTIONS:
            return entry, IDEMPOTENT_ACTIONS[(status, action)]

        target = LEGAL_TRANSITIONS.get((status, action))
        if target is None:
            allowed = NEXT_ACTIONS.get(status, ())
            hint = f"当前状态「{status}」仅允许：{'、'.join(allowed)}" if allowed else "当前状态无可执行动作"
            raise IllegalTransitionError(f"不允许从「{status}」执行「{action}」，状态只能单向推进；{hint}")

        if action == "启动接入":
            _open_next_batch(entry, resuming=status == "已暂停")
        elif action in ("暂停接入", "完成接入"):
            _close_active_batch(entry)

        entry["status"] = target
        _commit(entry)
        return entry, f"接入流水已{action}"


def ods_rows() -> list[dict[str, Any]]:
    """读取全部接入流水（含已归档），并保证字段已归一化。"""
    return [normalize_entry(row) for row in store.rows(ODS_MODULE)]


def find_ods_entry(entry_id: int) -> dict[str, Any] | None:
    for row in ods_rows():
        if int(row.get("id", 0)) == entry_id:
            return row
    return None


def admission_queue(
    *,
    keyword: str | None = None,
    status: str | None = None,
    admission: str | None = None,
) -> list[dict[str, Any]]:
    """明细清洗待办队列：由接入流水实时派生，已归档流水不出现。"""
    queue: list[dict[str, Any]] = []
    for entry in ods_rows():
        if entry.get("archived"):
            continue
        if keyword and keyword not in str(entry.get("流水编号", "")):
            continue
        if status and entry.get("status") != status:
            continue
        admitted, reason = admission_conclusion(entry)
        if admission == "可准入" and not admitted:
            continue
        if admission == "不可准入" and admitted:
            continue
        landing = str(entry.get("落地表名") or "")
        completed = entry.get("completed_batches") or []
        queue.append({
            "id": entry["id"],
            "version": entry["version"],
            "流水编号": entry.get("流水编号"),
            "输入表名": landing,
            "输出表名": f"{landing}_dwd" if landing else "",
            "接入状态": entry["status"],
            "分区水位": entry.get("partition_watermark") or "—",
            "执行批次": entry.get("active_batch") or (completed[-1] if completed else "—"),
            "可准入": "是" if admitted else "否",
            "准入结论": reason,
        })
    return queue
