# HeyBlog 项目结构说明

## 1. 项目定位

HeyBlog 是一个围绕“博客友链生态”构建的爬虫 MVP。项目当前以拆分服务形态运行为主：

- `frontend`
- `backend`
- `crawler`
- `search`
- `persistence_api`
- `persistence-db`

其中 `services/` 仍然保留为启动兼容层。

---

## 2. 顶层目录说明

### `backend/`

对外统一 API 聚合层。它不直接持久化数据，也不自己做爬取和搜索，而是通过 HTTP client 聚合内部服务，对前端暴露稳定的公开接口。

主要职责：

- 暴露 `/api/status`、`/api/blogs`、`/api/graph`、`/api/search`
- 转发 crawl/runtime 控制命令给 `crawler`
- 从 `persistence_api` 汇总博客、边、日志、统计信息
- 在爬取后触发 `search` 重建索引

关键文件：

- `backend/main.py`：后端服务主入口与 API 聚合逻辑。
- `backend/stats_service.py`：兼容导出，实际实现已下沉到 `persistence_api`。
- `backend/graph_service.py`：兼容导出，实际实现已下沉到 `persistence_api`。

### `crawler/`

爬虫服务实现目录，负责种子导入、博客抓取、友链页面发现、链接抽取、候选过滤、图关系写入，以及导出结果。

主要职责：

- 读取 `seed.csv` 导入初始博客
- 从待抓取队列取出博客
- 抓取首页并发现友链页面
- 访问候选友链页并抽取可接受的博客链接
- 将新博客和边写入持久化服务
- 导出 `nodes.csv`、`edges.csv`、`graph.json`

关键文件：

- `crawler/main.py`：Crawler HTTP 服务入口。
- `crawler/pipeline.py`：核心爬取流程编排。
- `crawler/runtime.py`：运行中状态与批次/持续运行控制。
- `crawler/fetcher.py`：页面抓取。
- `crawler/discovery.py`：友链页面发现。
- `crawler/extractor.py`：候选链接抽取。
- `crawler/filters.py`：候选博客过滤规则。
- `crawler/normalizer.py`：URL 归一化。
- `crawler/export_service.py`：图数据导出。
- `crawler/utils.py`：小型通用工具。

### `search/`

搜索服务实现目录。它本身不维护主数据源，而是从 `persistence_api` 拉取快照，构建一个轻量可重建的本地搜索索引。

主要职责：

- 拉取博客、边、日志快照
- 将快照写入本地缓存文件
- 提供简单关键字匹配搜索

关键文件：

- `search/main.py`：搜索服务入口、缓存索引重建与查询逻辑。

### `persistence_api/`

持久化服务目录，是数据读写的统一边界。对上游服务提供 HTTP 接口，对下游数据库隐藏 SQLite / PostgreSQL 的实现细节。

主要职责：

- 统一暴露博客、边、日志的增删查改接口
- 管理待抓取队列状态
- 提供统计视图与图结构视图
- 支持 SQLite 与 PostgreSQL 两种底层存储实现

关键文件：

- `persistence_api/main.py`：持久化服务 HTTP 入口。
- `persistence_api/repository.py`：仓储协议与 SQLite/PostgreSQL 实现。
- `persistence_api/schema.py`：数据库 schema 初始化。
- `persistence_api/stats_service.py`：统计聚合。
- `persistence_api/graph_service.py`：图结构聚合。

### `frontend/`

前端服务目录，包含两部分：

- `frontend/src/`：React + Vite 的前端页面源码
- `frontend/server.py`：FastAPI 前端服务，负责托管构建后的静态资源，并把 `/api/*` 代理到 `backend`

子目录作用：

- `frontend/src/pages/`：页面级组件，如统计页、博客页、控制页、运行态页、关于页。
- `frontend/src/components/`：可复用展示组件。
- `frontend/src/lib/`：前端 API 封装与 hooks。
- `frontend/src/shell/`：页面布局壳层。
- `frontend/src/test/`：前端测试初始化。

关键文件：

- `frontend/server.py`：前端服务入口和 API 代理。
- `frontend/src/lib/api.ts`：浏览器侧 API 调用封装。
- `frontend/src/router.tsx`：路由定义。
- `frontend/src/main.tsx`：前端应用入口。

### `services/`

拆分服务的启动兼容层。每个子目录只有一个很薄的 `main.py`，本质上只是重新导出顶层服务包的入口。它的存在是为了平滑迁移，不是业务实现目录。

子目录作用：

- `services/backend/`：兼容 `backend.main`
- `services/crawler/`：兼容 `crawler.main`
- `services/search/`：兼容 `search.main`
- `services/persistence/`：兼容 `persistence_api.main`
- `services/frontend/`：兼容 `frontend.server`

### `shared/`

跨服务共享代码目录，只允许放稳定、真正跨服务的通用能力。

子目录作用：

- `shared/http_clients/`：对 `crawler`、`search`、`persistence_api` 的 HTTP 调用封装。

关键文件：

- `shared/config.py`：统一环境变量与运行配置加载。
- `shared/BOUNDARY.md`：`shared/` 的边界约束说明。

### `tests/`

集中测试目录。当前测试更偏向拆分服务后的接口行为和核心爬虫逻辑回归。

覆盖范围包括：

- 爬虫发现、抽取、过滤、归一化逻辑
- 持久化仓储
- 拆分服务关键行为
- 服务拆分后的 API 形态是否保持稳定

### `doc/`

项目文档目录。用于存放结构说明、设计说明、运行说明等文档。

### `data/`

本地开发期的数据输出目录，主要用于本地运行时的 SQLite 数据与导出产物。

子目录作用：

- `data/exports/`：导出的图数据文件。

### `volumes/`

Docker Compose 挂载卷目录，用于让容器中的持久化数据落盘到本地。

子目录作用：

- `volumes/postgres/`：PostgreSQL 数据文件。
- `volumes/exports/`：爬虫导出文件。
- `volumes/search-cache/`：搜索服务索引缓存。

### `.github/`

GitHub 工作流与仓库自动化配置目录。

### `.omx/`

oh-my-codex 的状态、计划、日志与运行时元数据目录，不属于业务运行时核心逻辑，但属于当前仓库的协作基础设施。

### `build/`

本地构建产物目录，通常是打包或构建过程中生成的临时结果。

### `heyblog.egg-info/`

Python 包安装元数据目录，由打包/安装工具生成。

---

## 3. 各服务的职责边界

### `frontend`

面向用户的 Web 界面入口，负责页面展示和浏览器侧交互，不直接访问爬虫或数据库，而是统一调用 `backend`。

### `backend`

系统对外的统一 API 门户，负责聚合内部服务，对外屏蔽内部服务拆分细节。

### `crawler`

负责抓取和发现流程，是系统的“执行引擎”。

### `search`

负责轻量搜索能力，是系统的“查询加速层”。

### `persistence_api`

负责数据持久化与读模型聚合，是系统的“数据边界层”。

### `persistence-db`

在 Docker 拆分部署里由 PostgreSQL 承担真实数据库存储。

---

## 4. 服务之间如何联系

### 4.1 总体依赖关系

```text
浏览器
  -> frontend
  -> backend
     -> crawler
     -> search
     -> persistence_api
        -> persistence-db(PostgreSQL)
```

### 4.2 详细调用关系

1. 浏览器访问 `frontend`
2. `frontend/server.py` 提供静态页面，并把 `/api/*` 请求代理到 `backend`
3. `backend/main.py` 根据接口类型调用不同内部服务
4. `crawler` 在执行抓取时，通过 `shared/http_clients/persistence_http.py` 调用 `persistence_api`
5. `search` 通过 `persistence_api` 拉取搜索快照，构建本地缓存索引
6. `persistence_api` 通过 `repository.py` 访问 SQLite 或 PostgreSQL

### 4.3 典型链路一：启动一次爬取

```text
前端页面
  -> POST /api/crawl/bootstrap 或 /api/crawl/run
  -> frontend 代理到 backend
  -> backend 调 crawler 内部接口
  -> crawler.pipeline 执行导种/抓取
  -> crawler 通过 persistence_http 写入 blogs / edges / logs
  -> backend 在 run 完成后尝试调用 search.reindex()
```

说明：

- `backend` 是外部统一入口
- `crawler` 负责真正的抓取和发现
- `persistence_api` 负责保存抓取结果
- `search` 在抓取后刷新索引，保证搜索数据尽量新鲜

### 4.4 典型链路二：查看统计与图数据

```text
前端页面
  -> frontend
  -> backend /api/stats 或 /api/graph
  -> persistence_api /internal/stats 或 /internal/graph
  -> repository 读取数据库
  -> 返回给 backend
  -> 返回给 frontend
  -> 前端页面渲染
```

说明：

- 统计和图数据的组装逻辑已经收敛到 `persistence_api`
- `backend` 主要负责统一公开 API 形态，不重复实现数据聚合逻辑

### 4.5 典型链路三：搜索

```text
前端页面
  -> frontend
  -> backend /api/search?q=...
  -> search /internal/search?q=...
  -> 若本地缓存不存在，则 search 向 persistence_api 拉取快照
  -> search 返回匹配结果
```

说明：

- `search` 不是主数据源
- 主数据源仍然是 `persistence_api`
- `search` 更像一个可重建、可丢弃的缓存层

### 4.6 典型链路四：运行态控制

```text
前端页面
  -> backend /api/runtime/start|stop|status|current|run-batch
  -> crawler /internal/runtime/*
  -> crawler.runtime 维护当前运行状态
```

说明：

- 运行态控制由 `crawler.runtime` 负责
- `backend` 只做统一入口与向前端暴露

---

## 5. 配置与运行时组织方式

统一配置由 `shared/config.py` 中的 `Settings` 加载，核心环境变量包括：

- `HEYBLOG_BACKEND_BASE_URL`
- `HEYBLOG_CRAWLER_BASE_URL`
- `HEYBLOG_SEARCH_BASE_URL`
- `HEYBLOG_PERSISTENCE_BASE_URL`
- `HEYBLOG_DB_DSN`
- `HEYBLOG_DB_PATH`
- `HEYBLOG_SEED_PATH`
- `HEYBLOG_EXPORT_DIR`
- `HEYBLOG_SEARCH_CACHE_DIR`

这说明项目虽然拆分成多个服务，但配置入口是统一的，服务之间通过环境变量注入地址完成解耦。

---

## 6. 当前架构的几个关键设计点

### 对外统一、对内拆分

`backend` 是唯一建议暴露给前端或外部调用方的业务 API 入口，内部细分为 crawler、search、persistence 三类能力。

### 持久化边界单独抽离

`persistence_api` 不只是数据库 CRUD，还承担图结构和统计聚合，这样 `backend` 可以保持更薄，`crawler` 和 `search` 也不需要直接依赖数据库实现细节。

### 搜索是缓存层，不是主库

`search` 服务通过快照重建索引，因此它的状态丢失后可以重新生成，不承担系统事实来源职责。

### `services/` 是迁移过渡层

代码主线已经转向顶层服务包：

- `backend/`
- `crawler/`
- `search/`
- `persistence_api/`
- `frontend/`
- `shared/`

阅读和新增逻辑时，应优先从这些目录进入。

---

## 7. 推荐阅读顺序

如果是第一次接触这个项目，建议按下面顺序阅读：

1. `readme.md`：先理解项目目标与当前运行模式
2. `docker-compose.yml`：理解服务拓扑
3. `backend/main.py`：看公开 API 如何聚合内部服务
4. `crawler/pipeline.py`：看核心抓取流程
5. `persistence_api/main.py` + `persistence_api/repository.py`：看数据边界和存储实现
6. `search/main.py`：看搜索如何依赖快照
7. `frontend/server.py` + `frontend/src/lib/api.ts`：看前端如何接入后端

---

## 8. 一句话总结

这个仓库已经从“单体 FastAPI + SQLite”的早期形态，演进为“前端网关 + 后端聚合层 + 爬虫服务 + 搜索服务 + 持久化服务 + PostgreSQL”的拆分式结构；其中真正应该重点阅读和继续演进的是顶层服务包，`services/` 仅作为启动兼容层保留。
