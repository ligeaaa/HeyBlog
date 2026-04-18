# HeyBlog 开发与联调指南

这份文档面向日常开发，目标是回答 3 个问题：

- 怎么在本地快速跑起来
- 改某一部分时，最小需要启动哪些服务
- 改完之后，应该怎么测单点、怎么做联调

配套文档：

- `doc/project-structure.md`：看目录和主入口
- `doc/services-overview.md`：看服务职责和边界
- `doc/service-architecture.md`：看调用链
- `doc/api-docs.md`：看公共 API 和内部 API 契约
- `doc/config-reference.md`：看环境变量

## 1. 先理解项目怎么分层

真实实现都在这些顶层目录里：

- `frontend/`：React + Vite 前端源码，`frontend/server.py` 负责托管构建产物并代理 `/api/*`
- `backend/`：对外公共 API 聚合层
- `crawler/`：抓取、发现、抽取、过滤、导出、运行时控制
- `search/`：搜索索引和查询
- `persistence_api/`：数据读写、统计、图、搜索快照
- `shared/`：配置和跨服务 HTTP client

`services/` 只是兼容入口层，不建议继续放新业务代码。

## 2. Quick Start

### 2.1 安装基础依赖

先在仓库根目录准备 Python 环境：

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

如果你要改前端，再安装前端依赖：

```bash
cd frontend
npm install
cd ..
```

### 2.2 最短可用后端栈

如果你只是想调 API、crawler、search、persistence-api，而不需要浏览器面板，启动这 4 个服务就够了。

终端 1：

```bash
python -m uvicorn persistence_api.main:app --reload --port 8030
```

终端 2：

```bash
HEYBLOG_PERSISTENCE_BASE_URL=http://127.0.0.1:8030 \
HEYBLOG_SEED_PATH=$(pwd)/seed.csv \
HEYBLOG_EXPORT_DIR=$(pwd)/data/exports \
python -m uvicorn crawler.main:app --reload --port 8010
```

终端 3：

```bash
HEYBLOG_PERSISTENCE_BASE_URL=http://127.0.0.1:8030 \
HEYBLOG_SEARCH_CACHE_DIR=$(pwd)/data/search-cache \
python -m uvicorn search.main:app --reload --port 8020
```

终端 4：

```bash
HEYBLOG_PERSISTENCE_BASE_URL=http://127.0.0.1:8030 \
HEYBLOG_CRAWLER_BASE_URL=http://127.0.0.1:8010 \
HEYBLOG_SEARCH_BASE_URL=http://127.0.0.1:8020 \
python -m uvicorn backend.main:app --reload --port 8000
```

最基本的 smoke test：

```bash
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/stats
```

### 2.3 带浏览器面板的本地开发

如果你想用仓库自带的前端面板，但不依赖 Docker，可以先构建前端，再用 `frontend.server` 提供页面和 `/api` 代理。

先构建前端：

```bash
cd frontend
npm run build
cd ..
```

然后启动前端服务：

```bash
HEYBLOG_BACKEND_BASE_URL=http://127.0.0.1:8000 \
python -m uvicorn frontend.server:app --reload --port 3000
```

访问：

- 面板首页：`http://127.0.0.1:3000`
- 后端 API：`http://127.0.0.1:8000`

### 2.4 一键全量联调

如果你要验证完整拓扑，包括浏览器、后端、内部服务和 PostgreSQL，直接用 Docker：

```bash
docker compose up --build
```

默认端口：

- `frontend`: `3000`
- `backend`: `8000`
- `crawler`: `8010`
- `search`: `8020`
- `persistence-api`: `8030`
- `persistence-db`: `5432`

Docker 持久化目录：

- `volumes/postgres`
- `volumes/exports`
- `volumes/search-cache`

## 3. 本地开发时的一个关键原则

`shared/config.py` 的默认 URL 偏向 Docker 服务名，例如：

- `http://backend:8000`
- `http://crawler:8010`
- `http://search:8020`
- `http://persistence-api:8030`

所以你在宿主机直接运行 `uvicorn` 时，通常必须把相关环境变量改成 `127.0.0.1` 版本，否则服务之间会互相找不到。

## 4. 按改动范围选择开发方式

## 4.1 只改前端页面或交互

适用目录：

- `frontend/src/pages/`
- `frontend/src/components/`
- `frontend/src/router.tsx`
- `frontend/src/lib/api.ts`

推荐方式：

1. 先启动最短可用后端栈
2. 再运行 `npm run build`
3. 用 `frontend.server` 在 `3000` 端口访问页面

原因：

- 当前 `frontend/src/lib/api.ts` 走的是同源 `/api/*`
- 仓库里的 `vite.config.ts` 目前没有定义 `/api` 开发代理
- 所以单独 `npm run dev` 适合纯静态页面开发，不适合直接连真实后端

前端测试：

```bash
cd frontend
npm test
```

常看的测试文件：

- `frontend/src/App.test.tsx`
- `frontend/src/components/GraphVisualization.test.tsx`
- `frontend/src/pages/GraphPage.test.tsx`
- `frontend/src/components/graph/D3GraphCanvas.test.tsx`

页面联调建议：

- 统计页：打开 `/stats`
- 博客列表：打开 `/blogs`
- 详情页：点进单个 blog
- 控制页：打开 `/control`
- 搜索页：打开 `/search`
- 图谱页：打开 `/graph`

## 4.2 只改公共 API 或聚合逻辑

适用目录：

- `backend/main.py`
- `shared/http_clients/*.py`

最小启动集合：

- `persistence-api`
- `crawler`
- `search`
- `backend`

开发动作：

1. 改 `backend/main.py` 的 `/api/*`
2. 如果只是转发或聚合，不一定要改内部服务
3. 如果返回结构变了，要同步检查 `frontend/src/lib/api.ts` 和页面消费代码
4. 如果 API 契约变化了，要同步更新 `doc/api-docs.md`

建议验证：

```bash
curl http://127.0.0.1:8000/internal/health
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/blogs/catalog
curl "http://127.0.0.1:8000/api/graph/views/core?strategy=degree&limit=80"
```

对应后端回归测试：

```bash
pytest tests/test_service_split.py
```

## 4.3 只改 crawler

适用目录：

- `crawler/crawling/pipeline.py`
- `crawler/runtime/service.py`
- `crawler/crawling/fetching/httpx_fetcher.py`
- `crawler/crawling/discovery.py`
- `crawler/crawling/extraction.py`
- `crawler/filters.py`
- `crawler/crawling/normalization.py`
- `crawler/export_service.py`

最小启动集合：

- `persistence-api`
- `crawler`

如果你还要验证公共 API 或控制页，再加：

- `backend`
- `frontend`

常见验证顺序：

1. 导入种子

```bash
curl -X POST http://127.0.0.1:8010/internal/crawl/bootstrap
```

或者走公共 API：

```bash
curl -X POST http://127.0.0.1:8000/api/crawl/bootstrap
```

2. 执行一次同步抓取

```bash
curl -X POST "http://127.0.0.1:8010/internal/crawl/run?max_nodes=2"
```

或者：

```bash
curl -X POST "http://127.0.0.1:8000/api/admin/crawl/run?max_nodes=2"
```

3. 查看运行态

```bash
curl http://127.0.0.1:8010/internal/runtime/status
curl http://127.0.0.1:8000/api/admin/runtime/status
```

4. 检查导出文件

- `data/exports/nodes.csv`
- `data/exports/edges.csv`
- `data/exports/graph.json`

crawler 相关测试：

```bash
pytest tests/test_fetcher.py tests/test_discovery.py tests/test_extractor.py tests/test_filters.py tests/test_normalizer.py tests/test_pipeline.py tests/test_runtime.py tests/test_site_metadata.py
```

## 4.4 只改 persistence-api

适用目录：

- `persistence_api/main.py`
- `persistence_api/repository.py`
- `persistence_api/schema.py`
- `persistence_api/stats_service.py`
- `persistence_api/graph_service.py`
- `persistence_api/graph_projection.py`

最小启动集合：

- 只调内部数据接口时：`persistence-api`
- 如果要验证公共接口联动：再加 `backend`
- 如果要验证 crawler / search 联动：再加 `crawler`、`search`

常见验证：

```bash
curl http://127.0.0.1:8030/internal/health
curl http://127.0.0.1:8030/internal/stats
curl http://127.0.0.1:8030/internal/graph/views/core
curl http://127.0.0.1:8030/internal/search-snapshot
```

数据层相关测试：

```bash
pytest tests/test_repository.py tests/test_graph_projection.py tests/test_service_split.py
```

数据库说明：

- 不设置 `HEYBLOG_DB_DSN` 时，默认使用 SQLite
- 设置 `HEYBLOG_DB_DSN` 时，切到 PostgreSQL
- 本地轻开发优先用 SQLite
- 要验证 Docker 真正部署形态或 Postgres 差异，再用 `docker compose up --build`

## 4.5 只改 search

适用目录：

- `search/main.py`

最小启动集合：

- `persistence-api`
- `search`

如果要走公共 API：

- 再加 `backend`

常见验证：

```bash
curl -X POST http://127.0.0.1:8020/internal/search/reindex
curl "http://127.0.0.1:8020/internal/search?q=blog"
```

要关注的文件：

- 搜索缓存：`data/search-cache/search-index.json`

联动特点：

- `search` 不是事实来源
- 它先读本地缓存
- 缓存为空时，会回退到 `persistence-api /internal/search-snapshot`
- `backend` 在 crawl、batch、reset 后会尽力触发一次 reindex

## 4.6 做完整联调

如果你改的是跨服务链路，推荐按下面顺序验证：

1. 启动 `persistence-api`
2. 启动 `crawler`
3. 启动 `search`
4. 启动 `backend`
5. 如果要看页面，再构建并启动 `frontend`

推荐联调路径：

1. `POST /api/admin/crawl/bootstrap`
2. `POST /api/admin/crawl/run?max_nodes=...`
3. `GET /api/status`
4. `GET /api/blogs/catalog`
5. `GET /api/graph/views/core`
6. `GET /api/admin/runtime/status`

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/admin/crawl/bootstrap
curl -X POST "http://127.0.0.1:8000/api/admin/crawl/run?max_nodes=3"
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/blogs/catalog
curl "http://127.0.0.1:8000/api/graph/views/core?strategy=degree&limit=80"
curl http://127.0.0.1:8000/api/admin/runtime/status
```

## 5. 开发时怎么测

## 5.1 Python 测试

全量：

```bash
pytest
```

按模块缩小范围：

```bash
pytest tests/test_pipeline.py
pytest tests/test_runtime.py
pytest tests/test_repository.py
pytest tests/test_service_split.py
```

测试分工大致如下：

- `tests/test_fetcher.py`：抓取
- `tests/test_discovery.py`：友链页发现
- `tests/test_extractor.py`：链接抽取
- `tests/test_filters.py`：过滤规则
- `tests/test_normalizer.py`：URL 归一化
- `tests/test_pipeline.py`：crawl 主流程
- `tests/test_runtime.py`：后台运行器
- `tests/test_repository.py`：仓储与数据库行为
- `tests/test_graph_projection.py`：图投影与 snapshot
- `tests/test_service_split.py`：拆分服务与公共 API 形状回归
- `tests/test_site_metadata.py`：站点 metadata 行为

## 5.2 前端测试

```bash
cd frontend
npm test
```

如果你改了前端可见行为，除了跑测试，最好也重新构建一次：

```bash
cd frontend
npm run build
```

## 5.3 API smoke test

后端栈起来后，至少建议手动打这些接口：

```bash
curl http://127.0.0.1:8000/internal/health
curl http://127.0.0.1:8000/api/status
curl http://127.0.0.1:8000/api/stats
curl http://127.0.0.1:8000/api/blogs/catalog
curl http://127.0.0.1:8000/api/admin/runtime/status
```

如果你改了图谱或搜索，再补：

```bash
curl "http://127.0.0.1:8000/api/graph/views/core?strategy=degree&limit=80"
curl -X POST http://127.0.0.1:8020/internal/search/reindex
curl "http://127.0.0.1:8020/internal/search?q=blog"
```

## 6. 常见开发场景建议

## 6.1 我只想看页面，不想起 Docker

走下面组合：

- `persistence-api`
- `crawler`
- `search`
- `backend`
- `frontend.server`

这是最适合本地日常开发的一套。

## 6.2 我只想验证数据库或图查询

优先从 `persistence-api` 单独开始，必要时再挂上 `backend`。

这样定位问题最快，因为：

- `backend` 只是聚合层
- 图、统计、搜索快照的事实输出都在 `persistence-api`

## 6.3 我只想调 crawler 行为

先不要急着把整套前端也跑起来。

最小组合：

- `persistence-api`
- `crawler`

先把内部接口和测试打通，再决定要不要补 `backend` 和前端联调。

## 6.4 我要验证真实部署形态

直接用：

```bash
docker compose up --build
```

这时会带上 PostgreSQL，更接近拆分服务运行时。

## 7. 常见坑

1. 本地直接 `uvicorn` 时忘了把服务地址改成 `127.0.0.1`。
2. 以为 `frontend` 直接连 `crawler` 或 `persistence-api`，其实它只代理到 `backend`。
3. 以为 `search` 是事实来源，实际上它只是可重建缓存层。
4. 改了公共 API，但没同步更新 `frontend/src/lib/api.ts`。
5. 改了 API 契约，但没同步更新 `doc/api-docs.md`。
6. 只跑了 Python 测试，没跑前端测试或没重新构建前端。
7. 直接用 `npm run dev` 想连真实 API，但当前仓库没有现成的 Vite `/api` 代理。

## 8. 推荐的日常开发节奏

1. 先确定改动属于哪一层。
2. 只启动这层所需的最小依赖服务。
3. 先跑对应模块测试。
4. 再跑一次最小 smoke test。
5. 如果改动穿过服务边界，再补完整联调。
6. 如果改了前端可见行为，最后再跑 `frontend` 构建和页面手验。

这样比一上来就跑全套更快，也更容易定位问题。
