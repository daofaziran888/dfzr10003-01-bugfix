# 企业数据仓库管理平台

面向企业数据团队的一站式数据仓库建设与管理平台。覆盖原始数据落地、多层清洗转换、维度建模、事实建模、分区治理、质量校验、血缘追踪与历史补数的完整数仓链路。

这是一个前后端分离的管理平台：前端 React + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 React + Vite + TypeScript 前端
│   ├── src/views/            每个业务模块一个页面
│   ├── src/api/              统一请求封装
│   ├── src/stores/           会话与筛选状态
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/          每个业务模块一组接口
│   ├── app/services/         业务规则与状态流转
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm install
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 贴源层接入 | `ods` | 接入流水 | 流水编号、来源系统、源表名称 |
| 明细层清洗 | `dwd` | 清洗流水 | 流水编号、输入表名、输出表名 |
| 汇总层聚合 | `dws` | 聚合流水 | 流水编号、输入表名、输出表名 |
| 应用层输出 | `ads` | 输出流水 | 流水编号、输入表名、输出表名 |
| 维度定义管理 | `dimdef` | 维度定义 | 维度编号、维度名称、源表名称 |
| 事实表管理 | `factdef` | 事实定义 | 事实编号、事实名称、源表名称 |
| 分区策略 | `partition` | 分区配置 | 配置编号、表名称、分区字段 |
| 质量探针 | `quality` | 质量规则 | 规则编号、表名称、校验字段 |
| 血缘图谱 | `lineage` | 血缘节点 | 节点编号、节点名称、节点类型 |
| 历史重跑 | `backfill` | 重跑批次 | 批次编号、目标表名、开始日期 |
| 元数据目录 | `metadata` | 元数据记录 | 记录编号、表名称、字段名称 |
| ETL任务调度 | `etl` | 调度任务 | 任务编号、任务名称、依赖任务 |
| 数据湖存储 | `lake` | 湖存储节点 | 节点编号、存储路径、文件格式 |
| 表结构演进 | `catalog` | 演进记录 | 记录编号、表名称、变更类型 |
| 运行监控面板 | `monitor` | 监控指标 | 指标编号、指标名称、监控对象 |
| 快照管理 | `snapshot` | 快照记录 | 快照编号、表名称、快照时间 |

## 约定

- 每个模块的前端页面在 `frontend/src/views/<模块>/index.vue`，后端接口在
  `backend/app/routers/<模块>.py`，业务规则在 `backend/app/services/<模块>.py`。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

领域：数据工程
子方向：数仓与数据湖
