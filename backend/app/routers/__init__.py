"""业务模块路由汇总。

这里统一按别名导入再暴露 ROUTERS：模块名有可能和内置名撞车（某个业务模块就叫 dict、list
这种名字时），按名字直接 import 会把内置类型覆盖掉，函数注解在运行时求值就会报
'module' object is not subscriptable。
"""
from __future__ import annotations

from app.routers import ods as router_ods
from app.routers import dwd as router_dwd
from app.routers import dws as router_dws
from app.routers import ads as router_ads
from app.routers import dimdef as router_dimdef
from app.routers import factdef as router_factdef
from app.routers import partition as router_partition
from app.routers import quality as router_quality
from app.routers import lineage as router_lineage
from app.routers import backfill as router_backfill
from app.routers import metadata as router_metadata
from app.routers import etl as router_etl
from app.routers import lake as router_lake
from app.routers import catalog as router_catalog
from app.routers import monitor as router_monitor
from app.routers import snapshot as router_snapshot

ROUTERS = [router_ods, router_dwd, router_dws, router_ads, router_dimdef, router_factdef, router_partition, router_quality, router_lineage, router_backfill, router_metadata, router_etl, router_lake, router_catalog, router_monitor, router_snapshot]
