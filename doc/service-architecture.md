# HeyBlog 服务调用架构

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

其中：

- 浏览器只需要访问 `frontend`
- `frontend` 不直连数据库，也不直连 `crawler` / `search` / `persistence-api`
- `backend` 是公共 API 聚合层
- `persistence-api` 是系统事实来源边界
- `search` 是可重建缓存层，不是主库

## 2. 服务之间的调用方向

| 调用方 | 被调用方 | 方式 | 目的 |
| --- | --- | --- | --- |
| 浏览器 | `frontend` | HTTP | 获取页面资源与调用统一 `/api/*` 入口 |
| `frontend` | `backend` | HTTP 代理 | 转发浏览器的 `/api/*` 请求 |
| `backend` | `crawler` | HTTP client | 执行种子导入、批处理、运行时控制 |
| `backend` | `search` | HTTP client | 搜索查询、重建索引 |
| `backend` | `persistence-api` | HTTP client | 读取 blogs、edges、logs、stats、graph，执行 reset |
| `crawler` | `persistence-api` | HTTP client | 领取任务、写 blog、写 edge、写日志、导出图 |
| `search` | `persistence-api` | HTTP client | 拉取全量搜索快照 |
| `persistence-api` | SQLite / PostgreSQL | Repository | 持久化 blogs、edges、crawl_logs |

## 3. 真实代码中的调用边界

### 3.1 frontend -> backend

[frontend/server.py](/Users/lige/code/HeyBlog/frontend/server.py) 中的 `proxy_api()` 会把：

- `GET /api/{path}`
- `POST /api/{path}`

转发到 `HEYBLOG_BACKEND_BASE_URL/api/{path}`。

这意味着在当前实现里，浏览器拿到的是一个“静态资源服务 + API 代理层”的组合入口。

### 3.2 backend -> 内部服务

[backend/main.py](/Users/lige/code/HeyBlog/backend/main.py) 通过这三个 client 工作：

- [shared/http_clients/crawler_http.py](/Users/lige/code/HeyBlog/shared/http_clients/crawler_http.py)
- [shared/http_clients/search_http.py](/Users/lige/code/HeyBlog/shared/http_clients/search_http.py)
- [shared/http_clients/persistence_http.py](/Users/lige/code/HeyBlog/shared/http_clients/persistence_http.py)

它本身不直接操作仓储，也不直接 import `crawler` 的业务逻辑。

### 3.3 crawler/search -> persistence-api

`crawler` 和 `search` 都不直接访问数据库：

- `crawler` 通过 `PersistenceHttpClient` 调 `persistence-api`
- `search` 也通过 `PersistenceHttpClient` 调 `persistence-api`

因此数据库实现差异被集中收口在 `persistence_api/repository.py`。

### 3.4 persistence-api -> 存储后端

[persistence_api/repository.py](/Users/lige/code/HeyBlog/persistence_api/repository.py) 中：

- 未设置 `HEYBLOG_DB_DSN` 时使用 SQLite
- 设置了 `HEYBLOG_DB_DSN` 时使用 PostgreSQL

这让上游服务都只依赖 HTTP 契约，不依赖底层数据库细节。

## 4. 典型调用链

### 4.1 访问统计页

```text
浏览器
  -> frontend /stats
  -> 前端页面调用 /api/status 与 /api/stats
  -> frontend 代理到 backend
  -> backend 分别调用 persistence-api /internal/stats
  -> backend 额外调用 crawler /internal/runtime/status 组装 /api/status
  -> 返回给浏览器
```

补充：

- `StatsPage` 同时消费 `/api/status` 与 `/api/stats`
- `status.is_running` 并不是数据库字段，而是由 `crawler` 运行态推导

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

结果：

- `blogs` 表新增待抓取种子
- `crawl_logs` 表记录一次 `bootstrap` 日志

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

关键点：

- `queue/next` 同时完成“领取任务 + 标记为 PROCESSING”
- 搜索重建是尽力而为，失败不会让 crawl 主请求失败

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

说明：

- 运行器状态只保存在 `crawler` 进程内存中
- `current_blog_id`、`current_url`、`current_stage` 都来自 `CrawlerRuntimeService`

### 4.5 查询图谱

```text
浏览器 / GraphPage
  -> GET /api/graph
  -> frontend 代理到 backend
  -> backend -> persistence-api /internal/graph
  -> persistence-api.graph_service 读取 blogs + edges
  -> 返回 nodes/edges 给前端
  -> 前端用 Cytoscape 渲染
```

说明：

- 图数据的组装在 `persistence-api` 内部完成
- `backend` 只是暴露稳定的公共接口，不再重复拼装图结构

### 4.6 搜索

```text
浏览器 / SearchPage
  -> GET /api/search?q=keyword
  -> backend -> search /internal/search?q=keyword
  -> search 读取本地 search-index.json
  -> 若缓存不存在或为空，则回退到 persistence-api /internal/search-snapshot
  -> 返回 blogs / edges / logs 匹配结果
```

说明：

- 搜索服务是“可重建缓存层”
- 搜索页当前把 `blogs` 作为主结果区块，`edges/logs` 作为辅助信息区块

### 4.7 博客详情页

```text
浏览器 / BlogDetailPage
  -> GET /api/blogs/{blogId}
  -> GET /api/blogs
  -> GET /api/edges
  -> frontend 代理到 backend
  -> backend -> persistence-api 读取单 blog、全部 blogs、全部 edges
  -> 前端用 /api/blogs/{blogId} 渲染基础信息与 outgoing_edges
  -> 前端再基于 /api/blogs 建立 id -> domain 映射，并基于 /api/edges 计算 incoming_edges
```

说明：

- 当前详情页首版没有新增后端协议，而是在前端补齐入边展示
- 这是一个有意接受的 MVP 取舍；若边规模变大，可把 `incoming_edges` 下沉到后端

### 4.8 重置数据库

```text
浏览器 / 控制页
  -> POST /api/database/reset
  -> backend 先读取 crawler /internal/runtime/status
  -> 若 crawler 忙碌则返回 409 crawler_busy
  -> 否则 backend -> persistence-api /internal/database/reset
  -> persistence-api 清空 blogs / edges / crawl_logs
  -> backend 再尽力调用 search /internal/search/reindex
```

关键点：

- 重置动作由 `backend` 负责串起“运行态保护 + 数据重置 + 搜索重建”
- `persistence-api` 只负责自己的数据库边界

## 5. 数据归属

| 数据/状态 | 归属服务 | 说明 |
| --- | --- | --- |
| `blogs` / `edges` / `crawl_logs` | `persistence-api` | 系统事实来源 |
| `stats` / `graph` | `persistence-api` | 基于事实数据组装出的读模型 |
| `search-index.json` | `search` | 可重建缓存 |
| `RuntimeSnapshot` | `crawler` | 进程内内存态，不是持久化状态 |
| 页面路由与视图状态 | `frontend` | 浏览器界面层状态 |

## 6. 配置如何驱动调用关系

[shared/config.py](/Users/lige/code/HeyBlog/shared/config.py) 统一定义服务间地址与运行参数。当前关键环境变量包括：

- `HEYBLOG_BACKEND_BASE_URL`
- `HEYBLOG_CRAWLER_BASE_URL`
- `HEYBLOG_SEARCH_BASE_URL`
- `HEYBLOG_PERSISTENCE_BASE_URL`
- `HEYBLOG_DB_DSN`
- `HEYBLOG_DB_PATH`
- `HEYBLOG_SEED_PATH`
- `HEYBLOG_EXPORT_DIR`
- `HEYBLOG_SEARCH_CACHE_DIR`

这意味着：

- 服务间耦合主要通过 HTTP 地址注入，而不是模块直接引用
- 本地 SQLite 与容器内 PostgreSQL 的切换，主要由 `persistence-api` 内部吸收

## 7. 当前架构的实现观察

- `frontend` 代理层当前只支持 `GET` / `POST`，如果未来公共 API 增加 `PUT`、`PATCH`、`DELETE`，这里也需要同步扩展。
- `backend` 已经比较薄，更多像“公共协议门面 + 工作流串联器”。
- `crawler` 与 `search` 都通过 `persistence-api` 访问数据，这让数据边界保持集中，但也意味着 `persistence-api` 是整个系统的关键枢纽。
- 当前前端已覆盖统计、博客列表、博客详情、搜索、图谱、运行时与控制页；日志与全部 edge 列表仍主要停留在 API 层。
