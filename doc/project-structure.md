# HeyBlog 项目结构说明

## 适合谁看

- 第一次进入仓库、想先搞清楚目录和入口的新同学
- 想确认“代码应该改在哪一层”的开发者

## 建议前置阅读

- [README](../readme.md)
- [服务总览](./services-overview.md)

## 不包含什么

- 不展开讲每个服务的调用链细节，那部分见 [service-architecture.md](./service-architecture.md)
- 不逐条展开 HTTP 契约，那部分见 [api-docs.md](./api-docs.md)

## 最后核对源码入口

- [docker-compose.yml](../docker-compose.yml)
- [shared/config.py](../shared/config.py)
- [backend/main.py](../backend/main.py)
- [frontend/server.py](../frontend/server.py)

## 1. 当前仓库形态

HeyBlog 现在以“顶层服务包是主线，`services/` 是兼容层”的结构组织代码。
真正承载实现的是这些顶层目录：

- `frontend/`
- `backend/`
- `crawler/`
- `search/`
- `persistence_api/`
- `shared/`

`services/` 只保留启动兼容入口，不应该继续承载新业务逻辑。

## 2. 顶层目录总览

| 路径 | 当前角色 | 说明 |
| --- | --- | --- |
| `frontend/` | Public/Admin UI 与前端代理服务 | `frontend/src/` 是 React + Vite 源码，`frontend/server.py` 负责托管构建产物并代理 `/api/*`；当前前端已拆为 public/admin 双路由树 |
| `backend/` | 公共 API 聚合层 | 对外暴露公共 `/api/*`，通过 HTTP client 聚合 `crawler`、`search`、`persistence-api` |
| `crawler/` | 爬虫执行服务 | 负责种子导入、页面抓取、友链抽取、过滤、导出与运行时控制 |
| `search/` | 搜索服务 | 从 `persistence-api` 拉取快照并构建可重建缓存 |
| `persistence_api/` | 数据边界服务 | 统一 blog、edge、log、stats、graph 等数据读写与聚合 |
| `shared/` | 跨服务共享能力 | 当前主要承载配置与服务间 HTTP client |
| `services/` | 兼容入口层 | `services/*/main.py` 只是重新导出顶层服务入口 |
| `tests/` | 集中测试目录 | 覆盖爬虫流程、仓储行为、服务拆分回归与前端页面测试 |
| `doc/` | 文档目录 | 存放结构、服务、架构、API、配置与开发流程文档 |
| `data/` | 本地运行数据 | 默认 SQLite、导出目录、搜索缓存等 |
| `volumes/` | Docker 挂载卷 | PostgreSQL 数据、导出文件、搜索缓存等容器落盘目录 |

## 3. 源码主入口

### 3.1 运行时入口

| 服务 | 主要入口 | 说明 |
| --- | --- | --- |
| `frontend` | [frontend/server.py](../frontend/server.py) | 浏览器入口，托管前端构建产物并代理公共 API |
| `backend` | [backend/main.py](../backend/main.py) | 公共 API 聚合层 |
| `crawler` | [crawler/main.py](../crawler/main.py) | 爬虫执行与运行时控制 |
| `search` | [search/main.py](../search/main.py) | 搜索查询与索引重建 |
| `persistence-api` | [persistence_api/main.py](../persistence_api/main.py) | 数据读写、统计、图与快照边界 |
| `persistence-db` | [docker-compose.yml](../docker-compose.yml) 中的 `postgres:16` 服务 | 只在 Docker 拆分部署中存在 |

### 3.2 关键实现文件

- `crawler` 主流程： [crawler/crawling/pipeline.py](../crawler/crawling/pipeline.py)
- `crawler` 运行时： [crawler/runtime/service.py](../crawler/runtime/service.py)
- `persistence-api` 仓储实现： [persistence_api/repository.py](../persistence_api/repository.py)
- `persistence-api` 图聚合： [persistence_api/graph_service.py](../persistence_api/graph_service.py)
- 前端路由： [frontend/src/router.tsx](../frontend/src/router.tsx)
- Public/Admin 边界： [public-admin-boundary.md](./public-admin-boundary.md)
- 前端 API 封装： [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)

### 3.3 兼容层入口

这些文件存在的意义只是兼容历史启动路径：

- [services/backend/main.py](../services/backend/main.py)
- [services/crawler/main.py](../services/crawler/main.py)
- [services/search/main.py](../services/search/main.py)
- [services/persistence/main.py](../services/persistence/main.py)
- [services/frontend/main.py](../services/frontend/main.py)

如果你在决定“该把新代码放哪”，默认不要放进 `services/`。

## 4. 10 分钟阅读路径

1. 先看 [README](../readme.md) 里的三条启动路径，建立运行方式的整体认知。
2. 再看 [docker-compose.yml](../docker-compose.yml)，确认服务名、端口和容器依赖。
3. 接着读 [services-overview.md](./services-overview.md)，理解每个服务该负责什么。
4. 最后按 [service-architecture.md](./service-architecture.md) 和 [api-docs.md](./api-docs.md) 进入调用链和协议细节。

## 5. 当前结构的几个关键事实

- 顶层服务包已经是事实上的源码主线。
- `frontend/server.py` 同时承担浏览器入口与 API 代理层职责。
- `backend` 是公共协议门面，不直接操作数据库。
- `persistence_api/` 不只是 CRUD，还拥有 `stats`、`graph`、snapshot 这类读模型聚合。
- `search/` 是缓存层，不是系统事实来源。
- `shared/` 当前只有配置与跨服务 HTTP client 两类稳定共享能力。

## 6. 文档索引

- [services-overview.md](./services-overview.md)：服务职责、依赖关系、编辑边界
- [service-architecture.md](./service-architecture.md)：调用方向、典型链路、数据归属
- [api-docs.md](./api-docs.md)：公共 API 与内部 API 契约
- [config-reference.md](./config-reference.md)：环境变量、默认值与消费服务
- [developer-workflows.md](./developer-workflows.md)：常见开发任务入口
