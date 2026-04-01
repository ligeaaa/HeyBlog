# HeyBlog 服务总览

## 适合谁看

- 想快速判断“这个需求该改哪个服务”的开发者
- 想理解服务职责边界、而不是追调用细节的读者

## 建议前置阅读

- [README](../readme.md)
- [项目结构说明](./project-structure.md)

## 不包含什么

- 不展开逐条接口定义，那部分见 [api-docs.md](./api-docs.md)
- 不详细描述时序调用链，那部分见 [service-architecture.md](./service-architecture.md)

## 最后核对源码入口

- [backend/main.py](../backend/main.py)
- [crawler/main.py](../crawler/main.py)
- [search/main.py](../search/main.py)
- [persistence_api/main.py](../persistence_api/main.py)
- [frontend/server.py](../frontend/server.py)

## 1. 服务清单

| 服务 | 默认端口 | 入口 | 对谁提供能力 | 直接依赖 |
| --- | --- | --- | --- | --- |
| `frontend` | `3000` | [frontend/server.py](../frontend/server.py) | 浏览器 | `backend` |
| `backend` | `8000` | [backend/main.py](../backend/main.py) | 前端与外部调用方 | `crawler`、`search`、`persistence-api` |
| `crawler` | `8010` | [crawler/main.py](../crawler/main.py) | `backend` | `persistence-api` |
| `search` | `8020` | [search/main.py](../search/main.py) | `backend` | `persistence-api` |
| `persistence-api` | `8030` | [persistence_api/main.py](../persistence_api/main.py) | `backend`、`crawler`、`search` | SQLite 或 PostgreSQL |
| `persistence-db` | `5432` | [docker-compose.yml](../docker-compose.yml) 中的 Postgres 服务 | `persistence-api` | 本地卷 `volumes/postgres` |

## 2. frontend

### 2.1 职责

- 托管 `frontend/dist` 构建产物
- 把浏览器的 `/api/*` 请求代理到 `backend`
- 提供浏览器入口和健康检查

### 2.2 关键文件

- 服务入口： [frontend/server.py](../frontend/server.py)
- 前端源码入口： [frontend/src/main.tsx](../frontend/src/main.tsx)
- 路由定义： [frontend/src/router.tsx](../frontend/src/router.tsx)
- API 封装： [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)

### 2.3 什么时候改这里

- 改页面、路由、前端交互
- 改浏览器到后端的调用方式
- 改前端代理层行为

## 3. backend

### 3.1 职责

- 作为公共 API 聚合层，对外暴露稳定 `/api/*`
- 将 crawl / runtime 控制命令转发给 `crawler`
- 将搜索请求转发给 `search`
- 从 `persistence-api` 读取 blogs、edges、stats、graph、logs
- 在 crawl、batch、reset 后尽力触发一次搜索重建

### 3.2 关键文件

- 入口： [backend/main.py](../backend/main.py)
- `crawler` client： [shared/http_clients/crawler_http.py](../shared/http_clients/crawler_http.py)
- `search` client： [shared/http_clients/search_http.py](../shared/http_clients/search_http.py)
- `persistence` client： [shared/http_clients/persistence_http.py](../shared/http_clients/persistence_http.py)

### 3.3 什么时候改这里

- 新增或调整公共 API
- 公共工作流编排逻辑变化
- 跨服务聚合响应结构变化

## 4. crawler

### 4.1 职责

- 从 `seed.csv` 导入种子
- 抓取首页并发现友链页候选
- 从候选页抽取友链链接并过滤
- 将 blog / edge / log 写回 `persistence-api`
- 导出 `nodes.csv`、`edges.csv`、`graph.json`
- 提供同步执行与运行时控制两类能力

### 4.2 关键文件

- 服务入口： [crawler/main.py](../crawler/main.py)
- 执行流程： [crawler/pipeline.py](../crawler/pipeline.py)
- 运行时控制： [crawler/runtime.py](../crawler/runtime.py)
- 导出逻辑： [crawler/export_service.py](../crawler/export_service.py)
- 抓取： [crawler/fetcher.py](../crawler/fetcher.py)
- 发现： [crawler/discovery.py](../crawler/discovery.py)
- 抽取： [crawler/extractor.py](../crawler/extractor.py)
- 过滤： [crawler/filters.py](../crawler/filters.py)
- 归一化： [crawler/normalizer.py](../crawler/normalizer.py)

### 4.3 什么时候改这里

- 友链发现、抽取、过滤、归一化规则变化
- 导出逻辑变化
- 后台运行器与批处理行为变化

## 5. search

### 5.1 职责

- 从 `persistence-api` 拉取搜索快照
- 将快照落到本地缓存文件
- 对 blogs、edges、logs 做关键字匹配

### 5.2 关键文件

- 入口： [search/main.py](../search/main.py)

### 5.3 什么时候改这里

- 搜索结果结构变化
- 索引缓存路径、重建策略、回退策略变化
- 搜索匹配规则变化

## 6. persistence-api

### 6.1 职责

- 统一处理 blogs / edges / logs 的读写
- 管理待抓取队列状态
- 提供 `stats`、`graph`、graph snapshot 等读模型聚合
- 向上游隐藏 SQLite / PostgreSQL 实现差异

### 6.2 关键文件

- 服务入口： [persistence_api/main.py](../persistence_api/main.py)
- 仓储实现： [persistence_api/repository.py](../persistence_api/repository.py)
- Schema 初始化： [persistence_api/schema.py](../persistence_api/schema.py)
- 统计聚合： [persistence_api/stats_service.py](../persistence_api/stats_service.py)
- 图聚合： [persistence_api/graph_service.py](../persistence_api/graph_service.py)
- 图投影： [persistence_api/graph_projection.py](../persistence_api/graph_projection.py)

### 6.3 什么时候改这里

- 数据模型、仓储行为、统计逻辑、图查询逻辑变化
- SQLite / PostgreSQL 切换或持久化细节变化
- 内部 `/internal/*` 数据协议变化

## 7. persistence-db

`persistence-db` 不是 Python 包，而是 [docker-compose.yml](../docker-compose.yml) 中定义的
`postgres:16` 容器服务。它只在 Docker 拆分运行时生效，为 `persistence-api` 提供
PostgreSQL 存储。

## 8. services 兼容层

`services/` 下每个子目录都只保留了一层很薄的入口兼容：

- [services/backend/main.py](../services/backend/main.py)
- [services/crawler/main.py](../services/crawler/main.py)
- [services/search/main.py](../services/search/main.py)
- [services/persistence/main.py](../services/persistence/main.py)
- [services/frontend/main.py](../services/frontend/main.py)

这里不应该继续新增业务逻辑。

## 9. 继续往下读

- 想看调用链：读 [service-architecture.md](./service-architecture.md)
- 想看接口定义：读 [api-docs.md](./api-docs.md)
- 想查配置：读 [config-reference.md](./config-reference.md)
- 想找具体开发入口：读 [developer-workflows.md](./developer-workflows.md)
