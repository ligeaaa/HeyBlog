# HeyBlog 项目结构说明

## 1. 当前仓库形态

HeyBlog 目前以“拆分服务运行时”为主线组织代码。真正承载业务实现的是顶层服务包，而不是历史兼容层：

- `frontend/`：前端 UI 与前端代理服务
- `backend/`：对外统一 API 聚合层
- `crawler/`：爬取执行与运行时控制
- `search/`：轻量搜索缓存与重建
- `persistence_api/`：持久化边界、统计与图查询
- `services/`：仅保留启动兼容层，不承载新业务逻辑

如果要理解服务职责，请优先阅读：

- [services-overview.md](/Users/lige/code/HeyBlog/doc/services-overview.md)
- [service-architecture.md](/Users/lige/code/HeyBlog/doc/service-architecture.md)
- [api-docs.md](/Users/lige/code/HeyBlog/doc/api-docs.md)

## 2. 顶层目录总览

| 路径 | 当前角色 | 说明 |
| --- | --- | --- |
| `backend/` | 公共 API 聚合层 | 暴露 `/api/*`，通过 HTTP client 聚合 `crawler`、`search`、`persistence_api` |
| `crawler/` | 爬虫执行服务 | 负责种子导入、抓取、抽取、过滤、写入边与导出图数据 |
| `search/` | 搜索服务 | 从 `persistence_api` 拉取快照，构建可重建的本地索引缓存 |
| `persistence_api/` | 数据边界服务 | 提供 blog、edge、log、stats、graph 等内部接口，并屏蔽 SQLite / PostgreSQL 细节 |
| `frontend/` | UI 与前端代理服务 | `frontend/src/` 为 React + Vite 源码，`frontend/server.py` 为 FastAPI 代理与静态资源托管 |
| `shared/` | 跨服务共享能力 | 当前主要放统一配置与内部 HTTP client，避免放入业务实现 |
| `services/` | 兼容入口层 | `services/*/main.py` 只是重新导出顶层服务入口 |
| `tests/` | 集中测试目录 | 包含爬虫逻辑、仓储行为与拆分服务回归测试 |
| `doc/` | 文档目录 | 存放结构、API、服务与架构说明 |
| `data/` | 本地开发数据 | 默认 SQLite 文件、导出产物等本地运行数据 |
| `volumes/` | Docker 挂载卷 | PostgreSQL 数据、导出文件、搜索缓存等容器落盘目录 |
| `.github/` | 仓库自动化 | GitHub Actions 与仓库级配置 |
| `.omx/` | 协作运行时元数据 | oh-my-codex 状态、计划、日志与记忆数据 |
| `build/` | 构建产物 | 本地打包生成目录，非业务源码 |
| `heyblog.egg-info/` | 包元数据 | Python 打包安装生成目录 |

## 3. 每个服务的源码入口

| 服务 | 主要入口 | 说明 |
| --- | --- | --- |
| `frontend` | `frontend/server.py` | 提供 `/`、`/internal/health`，并把 `/api/*` 代理到 `backend` |
| `backend` | `backend/main.py` | 对外公开 API 的唯一业务入口 |
| `crawler` | `crawler/main.py` | 暴露内部爬取与运行时接口 |
| `search` | `search/main.py` | 暴露内部搜索与索引重建接口 |
| `persistence-api` | `persistence_api/main.py` | 暴露内部数据读写与聚合接口 |
| `persistence-db` | `docker-compose.yml` 中的 `postgres:16` 服务 | 只在拆分部署中存在，代码不在仓库内实现 |

## 4. 目录级阅读建议

### 4.1 先看运行拓扑

先读 [docker-compose.yml](/Users/lige/code/HeyBlog/docker-compose.yml)，确认端口、环境变量和容器依赖：

- `frontend`: `3000`
- `backend`: `8000`
- `crawler`: `8010`
- `search`: `8020`
- `persistence-api`: `8030`
- `persistence-db`: `5432`

### 4.2 再看服务边界

建议按下面顺序阅读源码：

1. [backend/main.py](/Users/lige/code/HeyBlog/backend/main.py)
2. [crawler/main.py](/Users/lige/code/HeyBlog/crawler/main.py)
3. [crawler/pipeline.py](/Users/lige/code/HeyBlog/crawler/pipeline.py)
4. [crawler/runtime.py](/Users/lige/code/HeyBlog/crawler/runtime.py)
5. [persistence_api/main.py](/Users/lige/code/HeyBlog/persistence_api/main.py)
6. [persistence_api/repository.py](/Users/lige/code/HeyBlog/persistence_api/repository.py)
7. [search/main.py](/Users/lige/code/HeyBlog/search/main.py)
8. [frontend/server.py](/Users/lige/code/HeyBlog/frontend/server.py)
9. [frontend/src/lib/api.ts](/Users/lige/code/HeyBlog/frontend/src/lib/api.ts)

### 4.3 最后看兼容层

`services/*/main.py` 仅用于兼容旧入口。例如：

- [services/backend/main.py](/Users/lige/code/HeyBlog/services/backend/main.py)
- [services/crawler/main.py](/Users/lige/code/HeyBlog/services/crawler/main.py)
- [services/search/main.py](/Users/lige/code/HeyBlog/services/search/main.py)
- [services/persistence/main.py](/Users/lige/code/HeyBlog/services/persistence/main.py)
- [services/frontend/main.py](/Users/lige/code/HeyBlog/services/frontend/main.py)

这里不应该继续新增业务逻辑。

## 5. 当前结构的几个关键事实

- 顶层服务包已经是事实上的源码主线，`services/` 只是薄兼容层。
- `backend/graph_service.py` 与 `backend/stats_service.py` 只是向 `persistence_api` 的兼容转发，不再是核心实现。
- `frontend/server.py` 既是静态资源服务，也是浏览器访问后端 API 的统一代理层。
- `persistence_api/` 承担的不只是 CRUD，还包括 `stats` 与 `graph` 这类读模型聚合。
- `search/` 是缓存式服务，不是系统事实来源；事实来源仍然是 `persistence_api` 背后的数据库。

## 6. 文档索引

- [services-overview.md](/Users/lige/code/HeyBlog/doc/services-overview.md)：按服务整理职责、入口、依赖与关键代码
- [service-architecture.md](/Users/lige/code/HeyBlog/doc/service-architecture.md)：描述服务之间的调用方向与典型链路
- [api-docs.md](/Users/lige/code/HeyBlog/doc/api-docs.md)：按 HTTP 接口整理公共 API 与内部 API
