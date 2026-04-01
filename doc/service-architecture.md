# HeyBlog 服务调用架构

## 适合谁看

- 想理解一次请求会穿过哪些服务的开发者
- 想查运行时数据流、状态归属和调用方向的读者

## 建议前置阅读

- [README](../readme.md)
- [项目结构说明](./project-structure.md)
- [服务总览](./services-overview.md)

## 不包含什么

- 不逐条展开 API 字段，那部分见 [api-docs.md](./api-docs.md)
- 不重复讲每个服务的职责介绍，那部分见 [services-overview.md](./services-overview.md)

## 最后核对源码入口

- [frontend/server.py](../frontend/server.py)
- [backend/main.py](../backend/main.py)
- [crawler/runtime.py](../crawler/runtime.py)
- [crawler/pipeline.py](../crawler/pipeline.py)
- [persistence_api/graph_service.py](../persistence_api/graph_service.py)

## 1. 总体拓扑

当前仓库的主运行形态是拆分服务：

```text
浏览器
  -> frontend
     -> backend
        -> crawler
        -> search
        -> persistence-api
           -> SQLite 或 PostgreSQL

crawler -> persistence-api
search  -> persistence-api
```

关键边界：

- 浏览器只访问 `frontend`
- `frontend` 不直接连数据库，也不直接调用 `crawler`、`search`、`persistence-api`
- `backend` 是公共 API 聚合层
- `persistence-api` 是系统事实来源边界
- `search` 是可重建缓存层，不是主库

## 2. 服务之间的调用方向

| 调用方 | 被调用方 | 方式 | 目的 |
| --- | --- | --- | --- |
| 浏览器 | `frontend` | HTTP | 获取页面资源与统一 `/api/*` 入口 |
| `frontend` | `backend` | HTTP 代理 | 转发浏览器的公共 API 请求 |
| `backend` | `crawler` | HTTP client | 执行种子导入、同步 crawl、运行时控制 |
| `backend` | `search` | HTTP client | 搜索查询、重建索引 |
| `backend` | `persistence-api` | HTTP client | 读取 blogs、edges、logs、stats、graph、snapshot |
| `crawler` | `persistence-api` | HTTP client | 领取任务、写 blog、写 edge、写日志、导出图 |
| `search` | `persistence-api` | HTTP client | 拉取搜索快照 |
| `persistence-api` | SQLite / PostgreSQL | Repository | 持久化事实数据与聚合读模型 |

## 3. 真实代码中的边界

### 3.1 frontend -> backend

[frontend/server.py](../frontend/server.py) 的 `proxy_api()` 目前只代理：

- `GET /api/{path}`
- `POST /api/{path}`

浏览器实际拿到的是“静态资源服务 + API 代理层”的统一入口。

### 3.2 backend -> 内部服务

[backend/main.py](../backend/main.py) 通过三个 client 工作：

- [shared/http_clients/crawler_http.py](../shared/http_clients/crawler_http.py)
- [shared/http_clients/search_http.py](../shared/http_clients/search_http.py)
- [shared/http_clients/persistence_http.py](../shared/http_clients/persistence_http.py)

它不直接 import crawler 业务逻辑，也不直接操作数据库。

### 3.3 crawler / search -> persistence-api

`crawler` 和 `search` 都不直接访问数据库，它们都通过 `PersistenceHttpClient`
调用 `persistence-api`。这让 SQLite / PostgreSQL 差异被集中收口在
[persistence_api/repository.py](../persistence_api/repository.py)。

### 3.4 persistence-api -> 存储后端

`persistence-api` 内部根据 [shared/config.py](../shared/config.py) 选择后端：

- 未设置 `HEYBLOG_DB_DSN` 时使用 SQLite
- 设置了 `HEYBLOG_DB_DSN` 时使用 PostgreSQL

## 4. 典型调用链

### 4.1 浏览器打开统计页

```text
浏览器
  -> frontend /stats
  -> 前端页面调用 /api/status 与 /api/stats
  -> frontend 代理到 backend
  -> backend 调用 persistence-api /internal/stats
  -> backend 调用 crawler /internal/runtime/status
  -> 返回聚合结果给浏览器
```

### 4.2 导入种子

```text
浏览器 / 控制页
  -> POST /api/crawl/bootstrap
  -> frontend 代理到 backend
  -> backend -> crawler /internal/crawl/bootstrap
  -> crawler.pipeline 读取 seed.csv
  -> crawler -> persistence-api /internal/blogs/upsert
  -> crawler -> persistence-api /internal/logs
```

### 4.3 执行一次同步 crawl

```text
浏览器 / 外部调用方
  -> POST /api/crawl/run?max_nodes=N
  -> backend -> crawler /internal/crawl/run
  -> crawler -> persistence-api /internal/queue/next
  -> crawler 抓取首页并发现友链页
  -> crawler 抽取候选链接并过滤
  -> crawler -> persistence-api /internal/blogs/upsert
  -> crawler -> persistence-api /internal/edges
  -> crawler -> persistence-api /internal/blogs/{id}/result
  -> crawler -> persistence-api /internal/logs
  -> crawler 写出 nodes.csv / edges.csv / graph.json
  -> backend 尝试调用 search /internal/search/reindex
```

### 4.4 启动后台运行器

```text
浏览器 / 控制页
  -> POST /api/runtime/start
  -> backend -> crawler /internal/runtime/start
  -> crawler.runtime 启动后台线程
  -> 后台线程循环调用 pipeline.run_once(max_nodes=1)
  -> 每处理完一个 blog，更新内存中的 RuntimeSnapshot
  -> 无待处理任务或收到 stop 信号后回到 idle
```

### 4.5 查询图谱

```text
浏览器 / GraphPage
  -> GET /api/graph/views/core 或 /api/graph/nodes/{id}/neighbors
  -> frontend 代理到 backend
  -> backend -> persistence-api 图相关内部接口
  -> persistence-api.graph_service 读取 blogs + edges
  -> 返回节点、边和视图元数据
  -> 前端用 Cytoscape 渲染
```

### 4.6 搜索

```text
浏览器 / SearchPage
  -> GET /api/search?q=keyword
  -> backend -> search /internal/search?q=keyword
  -> search 读取本地 search-index.json
  -> 若缓存不存在或为空，则回退到 persistence-api /internal/search-snapshot
  -> 返回 blogs / edges / logs 匹配结果
```

### 4.7 重置数据库

```text
浏览器 / 控制页
  -> POST /api/database/reset
  -> backend 先读取 crawler /internal/runtime/status
  -> 若 crawler 忙碌则返回 409 crawler_busy
  -> 否则 backend -> persistence-api /internal/database/reset
  -> persistence-api 清空 blogs / edges / crawl_logs
  -> backend 再尽力调用 search /internal/search/reindex
```

## 5. 数据归属

| 数据 / 状态 | 归属服务 | 说明 |
| --- | --- | --- |
| `blogs` / `edges` / `crawl_logs` | `persistence-api` | 系统事实来源 |
| `stats` / `graph` / graph snapshots | `persistence-api` | 基于事实数据组装出的读模型 |
| `search-index.json` | `search` | 可重建缓存 |
| `RuntimeSnapshot` | `crawler` | 进程内内存态，不是持久化状态 |
| 页面路由与视图状态 | `frontend` | 浏览器界面层状态 |

## 6. 配置如何驱动调用关系

[shared/config.py](../shared/config.py) 统一定义服务地址与运行参数。配置明细见
[config-reference.md](./config-reference.md)，这里只记住两个事实：

- 服务间耦合主要通过 HTTP 地址注入，而不是模块直接引用
- SQLite 与 PostgreSQL 的切换主要由 `persistence-api` 内部吸收

## 7. 当前架构的实现观察

- `frontend` 代理层当前只支持 `GET` / `POST`；如果公共 API 新增 `PUT`、`PATCH`、`DELETE`，这里需要同步扩展。
- `backend` 已经比较薄，更像“公共协议门面 + 工作流串联器”。
- `persistence-api` 是整个系统的数据枢纽，因此图、统计、搜索快照等变化通常都会落到这一层。
- 图页主路径已经偏向 graph view / snapshot，而不是只依赖 legacy 的全量 `/api/graph`。
