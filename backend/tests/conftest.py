"""pytest 公共夹具：每个用例前重置内存仓库，保证用例间互不污染。"""
from __future__ import annotations

import pytest

from app.seed import SEED_ROWS
from app.store import store


@pytest.fixture(autouse=True)
def reset_store() -> None:
    store._tables = {  # noqa: SLF001 - 测试中直接复位内存仓库
        name: [dict(row) for row in rows] for name, rows in SEED_ROWS.items()
    }
    yield
