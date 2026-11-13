"""明细层清洗业务规则：清洗准入清单直接由贴源层接入流水派生。

本模块不再维护独立于接入的第二份状态——接入状态是唯一事实来源，
两个入口通过 :mod:`app.services.flow_state` 得到同一条合法状态结论。
已归档的接入流水不会再出现在待清洗队列中。
"""
from __future__ import annotations

from typing import Any

from app.services import flow_state


class DwdService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        admission: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = flow_state.admission_queue(
            keyword=keyword, status=status, admission=admission
        )
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def list_all_for_export(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        admission: str | None = None,
    ) -> list[dict[str, Any]]:
        """导出与清洗页列表同口径，确保每条流水的准入结论完全一致。"""
        return flow_state.admission_queue(
            keyword=keyword, status=status, admission=admission
        )

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        for row in flow_state.admission_queue():
            if int(row.get("id", 0)) == entry_id:
                return row
        return None
