# HeyBlog 服务整理

## 1. 服务清单

| 服务 | 默认端口 | 入口 | 对谁提供能力 | 直接依赖 |
| --- | --- | --- | --- | --- |
| `frontend` | `3000` | [frontend/server.py](/Users/lige/code/HeyBlog/frontend/server.py) | 浏览器 | `backend` |
| `backend` | `8000` | [backend/main.py](/Users/lige/code/HeyBlog/backend/main.py) | 前端与外部调用方 | `crawler`、`search`、`persistence-api` |
| `crawler` | `8010` | [crawler/main.py](/Users/lige/code/HeyBlog/crawler/main.py) | `backend` | `persistence-api` |
| `search` | `8020` | [search/main.py](/Users/lige/code/HeyBlog/search/main.py) | `backend` | `persistence-api` |
| `persistence-api` | `8030` | [persistence_api/main.py](/Users/lige/code/HeyBlog/persistence_api/main.py) | `backend`、`crawler`、`search` | SQLite 或 PostgreSQL |
| `persistence-db` | `5432` | [docker-compose.yml](/Users/lige/code/HeyBlog/docker-compose.yml) 中的 Postgres 服务 | `persistence-api` | 本地卷 `volumes/postgres` |

## 2. frontend 服务

### 2.1 定位

`frontend` 是浏览器看到的入口，但它本身不实现业务 API。它做两件事：

- 托管 `frontend/dist` 中的静态前端资源
- 把浏览器发来的 `/api/*` 请求代理到 `backend`

### 2.2 代码入口

- 服务入口： [frontend/server.py](/Users/lige/code/HeyBlog/frontend/server.py)
- 前端源码入口： [frontend/src/main.tsx](/Users/lige/code/HeyBlog/frontend/src/main.tsx)
- 路由定义： [frontend/src/router.tsx](/Users/lige/code/HeyBlog/frontend/src/router.tsx)
- 浏览器 API 封装： [frontend/src/lib/api.ts](/Users/lige/code/HeyBlog/frontend/src/lib/api.ts)

### 2.3 当前页面

当前 React 路由包含：

- `/stats`
- `/blogs`
- `/graph`
- `/runtime/current`
- `/about`
- `/control`

对应源码位于：

- [frontend/src/pages/StatsPage.tsx](/Users/lige/code/HeyBlog/frontend/src/pages/StatsPage.tsx)
- [frontend/src/pages/BlogsPage.tsx](/Users/lige/code/HeyBlog/frontend/src/pages/BlogsPage.tsx)
- [frontend/src/pages/GraphPage.tsx](/Users/lige/code/HeyBlog/frontend/src/pages/GraphPage.tsx)
- [frontend/src/pages/CurrentRuntimePage.tsx](/Users/lige/code/HeyBlog/frontend/src/pages/CurrentRuntimePage.tsx)
- [frontend/src/pages/AboutPage.tsx](/Users/lige/code/HeyBlog/frontend/src/pages/AboutPage.tsx)
- [frontend/src/pages/ControlPage.tsx](/Users/lige/code/HeyBlog/frontend/src/pages/ControlPage.tsx)

### 2.4 当前实际调用的后端接口

浏览器侧封装目前使用的是这批公开 API：

- `/api/blogs`
- `/api/status`
- `/api/stats`
- `/api/graph`
- `/api/runtime/status`
- `/api/runtime/current`
- `/api/runtime/start`
- `/api/runtime/stop`
- `/api/runtime/run-batch`
- `/api/crawl/bootstrap`
- `/api/database/reset`

说明：

- 当前前端还没有搜索页面，因此虽然 `backend` 提供 `/api/search`，前端暂未直接消费。
- `frontend/server.py` 目前只代理 `GET` 和 `POST` 两类 `/api/*` 请求。

### 2.5 运行依赖

`frontend` 通过 `HEYBLOG_BACKEND_BASE_URL` 指向 `backend`，在 `docker-compose.yml` 中默认为 `http://backend:8000`。

## 3. backend 服务

### 3.1 定位

`backend` 是对外唯一建议暴露的业务 API 层。它不直接操作数据库，也不直接实现爬虫，而是：

- 从 `persistence-api` 读取 blogs、edges、stats、graph、logs
- 将 crawl 与 runtime 控制命令转发给 `crawler`
- 将搜索请求转发给 `search`
- 在 crawl / batch / reset 之后尽力触发一次搜索索引重建

### 3.2 代码入口

- 入口： [backend/main.py](/Users/lige/code/HeyBlog/backend/main.py)
- 内部 HTTP client：
  - [shared/http_clients/crawler_http.py](/Users/lige/code/HeyBlog/shared/http_clients/crawler_http.py)
  - [shared/http_clients/search_http.py](/Users/lige/code/HeyBlog/shared/http_clients/search_http.py)
  - [shared/http_clients/persistence_http.py](/Users/lige/code/HeyBlog/shared/http_clients/persistence_http.py)

### 3.3 对外提供的能力

主要公共接口包括：

- 状态与统计：`/api/status`、`/api/stats`
- 图查询：`/api/blogs`、`/api/blogs/{blog_id}`、`/api/edges`、`/api/graph`
- 搜索与日志：`/api/search`、`/api/logs`
- 爬取控制：`/api/crawl/bootstrap`、`/api/crawl/run`
- 运行时控制：`/api/runtime/status`、`/api/runtime/current`、`/api/runtime/start`、`/api/runtime/stop`、`/api/runtime/run-batch`
- 数据维护：`/api/database/reset`

### 3.4 当前实现中的边界

- `backend` 不保存系统主数据。
- `backend` 的健康检查不是自检，而是主动探测三个上游：`persistence`、`crawler`、`search`。
- [backend/graph_service.py](/Users/lige/code/HeyBlog/backend/graph_service.py) 与 [backend/stats_service.py](/Users/lige/code/HeyBlog/backend/stats_service.py) 只是兼容导出，真实实现已经在 `persistence_api/`。

## 4. crawler 服务

### 4.1 定位

`crawler` 是系统中的执行引擎，负责：

- 从 `seed.csv` 导入种子
- 从待处理队列中领取 blog
- 抓取首页，发现友链页候选
- 从友链页抽取候选链接
- 过滤候选，持久化 blog 与 edge
- 回写日志与抓取结果
- 导出 `nodes.csv`、`edges.csv`、`graph.json`

### 4.2 代码入口

- 服务入口： [crawler/main.py](/Users/lige/code/HeyBlog/crawler/main.py)
- 执行流程： [crawler/pipeline.py](/Users/lige/code/HeyBlog/crawler/pipeline.py)
- 运行时控制： [crawler/runtime.py](/Users/lige/code/HeyBlog/crawler/runtime.py)
- 导出： [crawler/export_service.py](/Users/lige/code/HeyBlog/crawler/export_service.py)

### 4.3 关键子模块

| 模块 | 职责 |
| --- | --- |
| [crawler/fetcher.py](/Users/lige/code/HeyBlog/crawler/fetcher.py) | 页面抓取 |
| [crawler/discovery.py](/Users/lige/code/HeyBlog/crawler/discovery.py) | 从首页发现友链页候选 |
| [crawler/extractor.py](/Users/lige/code/HeyBlog/crawler/extractor.py) | 从候选页抽取友链链接 |
| [crawler/filters.py](/Users/lige/code/HeyBlog/crawler/filters.py) | 执行过滤规则 |
| [crawler/normalizer.py](/Users/lige/code/HeyBlog/crawler/normalizer.py) | URL 归一化 |
| [crawler/utils.py](/Users/lige/code/HeyBlog/crawler/utils.py) | 小型通用工具 |

### 4.4 依赖关系

`crawler` 不直接连数据库，而是通过 [shared/http_clients/persistence_http.py](/Users/lige/code/HeyBlog/shared/http_clients/persistence_http.py) 调用 `persistence-api`。

它主要使用这些内部接口：

- `/internal/blogs/upsert`
- `/internal/queue/next`
- `/internal/blogs/{blog_id}/result`
- `/internal/logs`
- `/internal/blogs`
- `/internal/edges`

最后两项用于导出阶段读取完整节点与边数据。

### 4.5 运行模式

`crawler` 同时支持两种运行方式：

- 一次性批处理：`POST /internal/crawl/run`
- 带内存态快照的运行器模式：`/internal/runtime/start|stop|status|current|run-batch`

## 5. search 服务

### 5.1 定位

`search` 是一个轻量、可重建、允许丢失的缓存式服务。它不是主数据源，只负责：

- 从 `persistence-api` 拉取搜索快照
- 将快照写入本地缓存文件
- 对 blogs、edges、logs 做简单关键字匹配

### 5.2 代码入口

- 入口： [search/main.py](/Users/lige/code/HeyBlog/search/main.py)

### 5.3 数据来源

`search` 通过 [shared/http_clients/persistence_http.py](/Users/lige/code/HeyBlog/shared/http_clients/persistence_http.py) 调用：

- `GET /internal/search-snapshot`

并将结果落到 `HEYBLOG_SEARCH_CACHE_DIR/search-index.json`。

### 5.4 当前实现特征

- 查询词为空字符串时直接返回空结果。
- 如果缓存文件不存在或内容为空，会回退到 `persistence-api` 的实时快照。
- 索引重建通常由 `backend` 在 crawl / batch / reset 后顺手触发。

## 6. persistence-api 服务

### 6.1 定位

`persistence-api` 是系统的数据边界层，负责：

- 统一处理 blogs / edges / logs 的读写
- 管理待抓取队列状态
- 对外提供图结构与统计聚合
- 对上游服务隐藏 SQLite / PostgreSQL 实现差异

### 6.2 代码入口

- 服务入口： [persistence_api/main.py](/Users/lige/code/HeyBlog/persistence_api/main.py)
- 仓储实现： [persistence_api/repository.py](/Users/lige/code/HeyBlog/persistence_api/repository.py)
- Schema 初始化： [persistence_api/schema.py](/Users/lige/code/HeyBlog/persistence_api/schema.py)
- 统计聚合： [persistence_api/stats_service.py](/Users/lige/code/HeyBlog/persistence_api/stats_service.py)
- 图聚合： [persistence_api/graph_service.py](/Users/lige/code/HeyBlog/persistence_api/graph_service.py)

### 6.3 存储实现

当前代码支持两种后端：

- SQLite：默认使用 `HEYBLOG_DB_PATH`
- PostgreSQL：当设置 `HEYBLOG_DB_DSN` 时启用

在 Docker 拆分部署里，`persistence-api` 默认连接 `persistence-db` 容器中的 PostgreSQL。

### 6.4 数据边界特点

- `stats` 和 `graph` 的组装逻辑已经放到 `persistence_api/` 内部，不再由 `backend` 自己拼装。
- `GET /internal/queue/next` 既负责取下一个待抓取 blog，也负责把它立刻标记成 `PROCESSING`。
- `POST /internal/database/reset` 只清理 crawler 数据，不处理搜索缓存；搜索重建由上游 `backend` 负责串起来。

## 7. persistence-db 服务

### 7.1 定位

`persistence-db` 不是 Python 包，而是 [docker-compose.yml](/Users/lige/code/HeyBlog/docker-compose.yml) 中定义的 `postgres:16` 容器服务。

### 7.2 职责

- 为 `persistence-api` 提供 PostgreSQL 存储
- 将数据持久化到 `volumes/postgres`

### 7.3 何时生效

- 在 Docker Compose 拆分运行时生效
- 本地非 Docker 模式下，如果未设置 `HEYBLOG_DB_DSN`，则系统会退回 SQLite

## 8. services 兼容层

`services/` 下每个子目录都只有一层很薄的导出：

- [services/backend/main.py](/Users/lige/code/HeyBlog/services/backend/main.py)
- [services/crawler/main.py](/Users/lige/code/HeyBlog/services/crawler/main.py)
- [services/search/main.py](/Users/lige/code/HeyBlog/services/search/main.py)
- [services/persistence/main.py](/Users/lige/code/HeyBlog/services/persistence/main.py)
- [services/frontend/main.py](/Users/lige/code/HeyBlog/services/frontend/main.py)

它们的作用是兼容旧入口，不应继续承担新的业务实现。
