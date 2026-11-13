"""贴源层接入接口：维护接入流水，覆盖启动接入、暂停接入、完成接入、归档等动作。

注意 ``/export`` 必须声明在 ``/{entry_id}`` 之前，否则 "export" 会被
整数路径参数截获并返回 422（线上「路径参数必须为整数」故障的根因）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.routers.export_utils import ODS_EXPORT_COLUMNS, csv_response
from app.schemas import ActionPayload, ActionResult, EntryPayload, PageResult
from app.services.ods import OdsService

router = APIRouter(prefix="/api/ods", tags=["贴源层接入"])

service = OdsService()

LIST_FIELDS = ["流水编号", "来源系统", "源表名称", "落地表名", "接入周期", "分区粒度", "保留天数", "最近接入时间"]
STATUSES = ["草稿", "运行中", "已暂停", "已完成"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按流水编号检索"),
    status: str | None = Query(default=None, description="草稿、运行中、已暂停、已完成"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按流水编号与状态过滤贴源层接入列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不合法，可选：{'、'.join(STATUSES)}")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


# 导出路由必须排在 /{entry_id} 动态路由之前
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按流水编号检索"),
    status: str | None = Query(default=None, description="草稿、运行中、已暂停、已完成"),
):
    """导出当前全部接入流水为 CSV 文件，状态与准入口径和列表完全一致。"""
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不合法，可选：{'、'.join(STATUSES)}")
    items = service.list_all_for_export(keyword=keyword, status=status)
    return csv_response(items, filename="ods_access_entries.csv", columns=ODS_EXPORT_COLUMNS)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条接入流水明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"接入流水 {entry_id} 不存在")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条接入流水，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="接入流水已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    """对单条接入流水执行动作；非法流转、版本冲突都会被拦下并说明原因。"""
    action = str(payload.action or "").strip()
    entry, message, conflict_status = service.run_action(
        entry_id, action, expected_version=payload.expected_version
    )
    if conflict_status == 409:
        raise HTTPException(status_code=409, detail=message)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
