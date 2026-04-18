# HeyBlog 开发者任务索引

## 适合谁看

- 已经知道仓库大致结构，但想快速找到“这类任务从哪里下手”的开发者
- 想减少在多份文档之间来回跳转的读者

## 建议前置阅读

- [README](../readme.md)
- [项目结构说明](./project-structure.md)

## 不包含什么

- 不逐条重复 API 契约内容，那部分见 [api-docs.md](./api-docs.md)
- 不讲完整架构背景，那部分见 [service-architecture.md](./service-architecture.md)

## 最后核对源码入口

- [backend/main.py](../backend/main.py)
- [crawler/crawling/pipeline.py](../crawler/crawling/pipeline.py)
- [persistence_api/graph_service.py](../persistence_api/graph_service.py)
- [search/main.py](../search/main.py)
- [shared/config.py](../shared/config.py)

## 1. 我要新增或调整公共 API

先看：

- [api-docs.md](./api-docs.md)
- [backend/main.py](../backend/main.py)
- [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)

通常改动顺序：

1. 在 `backend/main.py` 增加或调整公共 `/api/*` 路由。
2. 如果需要下游能力，再去改 `crawler`、`search` 或 `persistence-api` 的 `/internal/*`。
3. 同步更新前端 API 封装与调用页面。
4. 同步更新 [api-docs.md](./api-docs.md)。

## 2. 我要调 crawler

先看：

- [crawler/main.py](../crawler/main.py)
- [crawler/crawling/pipeline.py](../crawler/crawling/pipeline.py)
- [crawler/runtime/service.py](../crawler/runtime/service.py)

常见落点：

- 抓取行为： [crawler/crawling/fetching/httpx_fetcher.py](../crawler/crawling/fetching/httpx_fetcher.py)
- 友链页发现： [crawler/crawling/discovery.py](../crawler/crawling/discovery.py)
- 链接抽取： [crawler/crawling/extraction.py](../crawler/crawling/extraction.py)
- 过滤规则： [crawler/filters.py](../crawler/filters.py)
- URL 归一化： [crawler/crawling/normalization.py](../crawler/crawling/normalization.py)
- 导出逻辑： [crawler/export_service.py](../crawler/export_service.py)

## 3. 我要查 graph 链路

先看：

- [persistence_api/graph_service.py](../persistence_api/graph_service.py)
- [persistence_api/graph_projection.py](../persistence_api/graph_projection.py)
- [backend/main.py](../backend/main.py)
- [frontend/src/pages/GraphPage.tsx](../frontend/src/pages/GraphPage.tsx)
- [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)

判断原则：

- 图数据的事实来源和视图组装在 `persistence-api`
- `backend` 负责把这些能力暴露成公共 `/api/graph*`
- 前端只负责参数组织、交互和渲染

如果你要讨论未来能力规划，再看：

- [prd-graph-community-discovery.md](./prd-graph-community-discovery.md)

## 4. 我要看搜索索引链路

先看：

- [backend/main.py](../backend/main.py)
- [search/main.py](../search/main.py)
- [persistence_api/main.py](../persistence_api/main.py)

链路顺序：

`backend` 在 health 检查、crawl run、runtime batch、database reset 后触发 `search` 读/重建索引 -> `search` 读取 `search-index.json`，缓存为空时回退到 `persistence-api /internal/search-snapshot`

## 5. 我要调 runtime / 控制台

先看：

- [frontend/src/pages/AdminPage.tsx](../frontend/src/pages/AdminPage.tsx)
- [backend/main.py](../backend/main.py)
- [crawler/runtime/service.py](../crawler/runtime/service.py)

重点记住：

- 运行器状态保存在 `crawler` 进程内存里
- `backend` 只负责把 runtime 能力暴露成公共接口
- 重置数据库前，`backend` 会先检查 runtime 是否忙碌

## 6. 我要重置数据或理解本地状态

先看：

- [backend/main.py](../backend/main.py)
- [persistence_api/main.py](../persistence_api/main.py)
- [config-reference.md](./config-reference.md)
- [docker-compose.yml](../docker-compose.yml)

相关状态位置：

- SQLite：`data/heyblog.sqlite`
- 导出目录：`data/exports/` 或 `volumes/exports/`
- 搜索缓存：`data/search-cache/` 或 `volumes/search-cache/`
- PostgreSQL 卷：`volumes/postgres/`

## 7. 我要改前端页面

先看：

- [frontend/src/router.tsx](../frontend/src/router.tsx)
- [frontend/src/shell/AppLayout.tsx](../frontend/src/shell/AppLayout.tsx)
- 对应页面文件，例如 [frontend/src/pages/StatsPage.tsx](../frontend/src/pages/StatsPage.tsx)

如果页面需要新数据：

1. 先确认公共 API 是否已经存在。
2. 没有的话，回到“我要新增或调整公共 API”这条流程。

## 8. 我要查配置或运行异常

先看：

- [config-reference.md](./config-reference.md)
- [shared/config.py](../shared/config.py)
- [docker-compose.yml](../docker-compose.yml)

优先核对：

- 服务基地址是否指到了正确端口
- 本地 `uvicorn` 启动时是否把 Docker 默认主机名改成了 `127.0.0.1`
- `HEYBLOG_DB_DSN` 是否意外覆盖了 SQLite 模式

## 9. 常用配套文档

- [services-overview.md](./services-overview.md)
- [service-architecture.md](./service-architecture.md)
- [api-docs.md](./api-docs.md)
- [config-reference.md](./config-reference.md)
