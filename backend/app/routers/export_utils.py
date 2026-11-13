"""网页导出辅助：把清单渲染成带 BOM 的 CSV 文件响应。

通过 Content-Disposition 让浏览器直接触发文件下载，而不是打开一段 JSON。
"""
from __future__ import annotations

import csv
import io
from typing import Any

from fastapi.responses import StreamingResponse

# 与列表/清洗页共用的列：先业务列，再统一附加状态与准入结论
ODS_EXPORT_COLUMNS = [
    "流水编号", "来源系统", "源表名称", "落地表名", "接入周期",
    "分区粒度", "保留天数", "最近接入时间",
    "status", "分区水位", "归档标记", "可准入", "准入结论",
]

DWD_EXPORT_COLUMNS = [
    "流水编号", "输入表名", "输出表名", "接入状态", "分区水位",
    "执行批次", "可准入", "准入结论",
]


def csv_response(
    rows: list[dict[str, Any]],
    *,
    filename: str,
    columns: list[str],
) -> StreamingResponse:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({column: _stringify(row.get(column)) for column in columns})
    # utf-8-sig 自动写入 BOM，Excel 打开中文不乱码
    payload = buffer.getvalue().encode("utf-8-sig")
    return StreamingResponse(
        iter([payload]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return "|".join(str(item) for item in value)
    return str(value)
