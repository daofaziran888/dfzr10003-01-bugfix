"""明细层清洗接口：展示由贴源层接入状态实时派生的清洗准入清单。

准入结论不在本模块单独维护，统一调用共享状态引擎，保证与贴源层列表、
导出读到同一条合法状态结论；已归档流水不会出现在队列中。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.routers.export_utils import DWD_EXPORT_COLUMNS, csv_response
from app.schemas import PageResult
from app.services.dwd import DwdService

router = APIRouter(prefix="/api/dwd", tags=["明细层清洗"])

service = DwdService()

LIST_FIELDS = ["流水编号", "输入表名", "输出表名", "接入状态", "分区水位", "执行批次", "可准入", "准入结论"]
STATUSES = ["草稿", "运行中", "已暂停", "已完成"]
ADMISSION_OPTIONS = ["可准入", "不可准入"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按流水编号检索"),
    status: str | None = Query(default=None, description="草稿、运行中、已暂停、已完成"),
    admission: str | None = Query(default=None, description="可准入、不可准入"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """读取清洗准入清单；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不合法，可选：{'、'.join(STATUSES)}")
    if admission and admission not in ADMISSION_OPTIONS:
        raise HTTPException(
            status_code=400, detail=f"准入条件「{admission}」不合法，可选：{'、'.join(ADMISSION_OPTIONS)}"
        )
    items, total = service.list_entries(
        keyword=keyword, status=status, admission=admission, page=page, size=size
    )
    return PageResult(items=items, total=total, page=page, size=size)


# 导出路由必须排在 /{entry_id} 动态路由之前，避免被整数路径参数截获
@router.get("/export")
def export_entries(
    keyword: str | None = Query(default=None, description="按流水编号检索"),
    status: str | None = Query(default=None, description="草稿、运行中、已暂停、已完成"),
    admission: str | None = Query(default=None, description="可准入、不可准入"),
):
    """导出清洗准入清单 CSV，与页面当次可见的准入结论完全一致。"""
    if status and status not in STATUSES:
        raise HTTPException(status_code=400, detail=f"状态「{status}」不合法，可选：{'、'.join(STATUSES)}")
    if admission and admission not in ADMISSION_OPTIONS:
        raise HTTPException(
            status_code=400, detail=f"准入条件「{admission}」不合法，可选：{'、'.join(ADMISSION_OPTIONS)}"
        )
    items = service.list_all_for_export(keyword=keyword, status=status, admission=admission)
    return csv_response(items, filename="dwd_admission_entries.csv", columns=DWD_EXPORT_COLUMNS)


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条清洗准入明细；已归档流水不在队列中，按不存在处理。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"清洗准入记录 {entry_id} 不存在或对应流水已归档")
    return entry
