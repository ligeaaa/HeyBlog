# HeyBlog API 文档

## 1. 文档目的

这份文档基于当前仓库源码整理 HeyBlog 已实现的 HTTP API，目标是帮助后续统筹时快速看清：

- 哪些是前端/外部应该调用的公共 API
- 哪些是拆分服务之间使用的内部 API
- 每个接口的请求参数、返回结构和职责边界
- 服务之间的调用链与典型执行流程

当前代码实现对应的服务分层如下：

- `frontend`：前端与操作面板
- `backend`：统一对外 API 聚合层
- `crawler`：爬虫执行与运行时控制
- `search`：搜索索引与查询
- `persistence-api`：持久化读写接口
- `persistence-db`：PostgreSQL 数据库

如果需要先从服务视角阅读，再回来看接口细节，建议配合下面两份文档：

- [project-structure.md](/Users/lige/code/HeyBlog/doc/project-structure.md)
- [services-overview.md](/Users/lige/code/HeyBlog/doc/services-overview.md)
- [service-architecture.md](/Users/lige/code/HeyBlog/doc/service-architecture.md)

默认端口来自 [docker-compose.yml](/Users/lige/code/HeyBlog/docker-compose.yml)：

- `frontend`: `3000`
- `backend`: `8000`
- `crawler`: `8010`
- `search`: `8020`
- `persistence-api`: `8030`
- `persistence-db`: `5432`

## 2. API 分层总览

### 2.1 公共 API

公共 API 由 `backend` 服务统一暴露，前端当前直接调用的就是这一层：

- `GET /`
- `GET /internal/health`
- `GET /api/status`
- `GET /api/blogs`
- `GET /api/blogs/{blog_id}`
- `GET /api/edges`
- `GET /api/graph`
- `GET /api/graph/views/core`
- `GET /api/graph/nodes/{blog_id}/neighbors`
- `GET /api/graph/snapshots/latest`
- `GET /api/graph/snapshots/{version}`
- `GET /api/stats`
- `GET /api/logs`
- `POST /api/crawl/bootstrap`
- `POST /api/crawl/run`
- `GET /api/search`
- `GET /api/runtime/status`
- `GET /api/runtime/current`
- `POST /api/runtime/start`
- `POST /api/runtime/stop`
- `POST /api/runtime/run-batch`
- `POST /api/database/reset`

源码位置： [backend/main.py](/Users/lige/code/HeyBlog/backend/main.py)

补充说明：

- 浏览器实际访问的是 `frontend` 服务。
- [frontend/server.py](/Users/lige/code/HeyBlog/frontend/server.py) 会把 `/api/*` 代理到 `backend`。
- 因此“公共 API 由 backend 提供”与“浏览器经 frontend 访问 API”这两件事同时成立。

### 2.2 内部服务 API

拆分架构下，`backend` 通过 HTTP 调用三个内部服务：

- `crawler` 内部接口：执行抓取、控制运行时
- `search` 内部接口：查询索引、重建索引
- `persistence-api` 内部接口：读写 blog、edge、log 以及聚合统计

这些接口都以 `/internal/*` 命名，原则上不应作为前端直接依赖的长期协议。

## 3. 公共 API 详细说明

### 3.1 根与健康检查

#### `GET /`

用途：返回后端服务的基础入口信息。

响应示例：

```json
{
  "name": "HeyBlog Backend",
  "status": "/api/status",
  "panel": "served-by-frontend"
}
```

#### `GET /internal/health`

用途：后端聚合健康检查。该接口会主动探测：

- persistence 的 `stats()`
- crawler 的 `runtime_status()`
- search 的 `search("")`

只要任一上游服务异常，后端会返回 `503`.

成功响应：

```json
{
  "status": "ok"
}
```

### 3.2 状态与统计接口

#### `GET /api/status`

用途：返回适合操作面板使用的简化状态。

返回字段：

- `is_running`: 是否处于 `starting/running/stopping`
- `pending_tasks`: 等待中的博客数
- `processing_tasks`: 处理中博客数
- `finished_tasks`: 已完成博客数
- `failed_tasks`: 失败博客数
- `total_blogs`: blog 总数
- `total_edges`: edge 总数

数据来源：

- 统计字段来自 `persistence-api /internal/stats`
- `is_running` 来自 `crawler /internal/runtime/status`

#### `GET /api/stats`

用途：返回完整统计信息。

返回字段：

- `total_blogs`
- `total_edges`
- `max_depth`
- `average_friend_links`
- `status_counts`
- `pending_tasks`
- `processing_tasks`
- `failed_tasks`
- `finished_tasks`

字段语义：

- `max_depth`: 当前已入库 blog 的最大深度
- `average_friend_links`: blog 的平均友链发现数
- `status_counts`: 按 `crawl_status` 分组后的原始计数

### 3.3 Blog 与图结构查询

#### `GET /api/blogs`

用途：返回所有 blog 节点列表。

返回数组元素结构见“数据模型”章节中的 `BlogRecord`。

补充说明：

- 每条记录都包含 `title` 与 `icon_url`。
- `title` 来自站点主页的 `<title>`。
- `icon_url` 优先使用主页里声明的 icon 链接；若页面未声明，当前实现会乐观回退到 `${origin}/favicon.ico`。
- 这两个字段都允许为 `null`，前端应回退到 `domain` 与默认占位图标。

#### `GET /api/blogs/{blog_id}`

用途：返回单个 blog 详情，并追加该 blog 的出边列表。

行为说明：

- 若 blog 不存在，返回 `404`
- 返回内容基于单 blog 记录扩展了 `outgoing_edges`

额外字段：

- `outgoing_edges`: 所有 `from_blog_id == blog_id` 的边

前端现状：

- 当前博客详情页直接消费该接口作为主数据源
- 首版详情页没有要求后端返回 `incoming_edges`
- 页面会额外结合 `GET /api/blogs` 与 `GET /api/edges` 在前端计算入边与相邻博客名称映射

#### `GET /api/edges`

用途：返回当前所有图边。

返回数组元素结构见“数据模型”章节中的 `EdgeRecord`。

#### `GET /api/graph`

用途：返回完整图数据，适合可视化或导出。

响应结构：

```json
{
  "nodes": [],
  "edges": []
}
```

其中：

- `nodes` 来自 blog 列表
- `edges` 来自 edge 列表
- `nodes` 中的每个 blog 记录同样包含 `title` 与 `icon_url`

补充说明：

- 这是 legacy 全量接口，当前图页默认入口已经不再依赖它
- 主要保留给回退路径、导出和调试场景

#### `GET /api/graph/views/core`

用途：返回图页默认使用的结构化初始子图。

常用查询参数：

- `strategy`: `degree` 或 `seed`
- `limit`: 默认子图规模上限
- `sample_mode`: `off` / `count` / `percent`
- `sample_value`: 当采样开启时的数量或百分比
- `sample_seed`: 固定随机种子，便于复现

响应结构：

```json
{
  "nodes": [],
  "edges": [],
  "meta": {
    "strategy": "degree",
    "limit": 180,
    "sample_mode": "off",
    "sample_value": null,
    "sample_seed": 7,
    "sampled": false,
    "focus_node_id": null,
    "hops": null,
    "has_stable_positions": true,
    "snapshot_version": "20260331T000000000000Z",
    "generated_at": "2026-03-31T00:00:00+00:00",
    "source": "snapshot",
    "total_nodes": 5306,
    "total_edges": 9758,
    "available_nodes": 5306,
    "available_edges": 9758,
    "selected_nodes": 180,
    "selected_edges": 264,
    "graph_fingerprint": "4d9c...a1f3"
  }
}
```

说明：

- `nodes` 元素沿用 `BlogRecord`，并额外携带 `x`、`y`、`degree`、`incoming_count`、`outgoing_count`、`priority_score`、`component_id`
- 当 `has_stable_positions` 为 `true` 时，前端会优先使用这些坐标直接渲染，而不是首次实时跑力导布局
- 当 `sample_mode != off` 时，会返回可复现的随机子图视图，但该模式只是辅助开关，不是默认主路径
- 服务在返回前会检查底层 graph 是否已变化；若当前仓库数据与最新 snapshot 不一致，会先重建 snapshot，再返回最新视图
- `graph_fingerprint` 是用于判定 graph 是否变更的稳定摘要，前端可把它当作视图身份的一部分，但不应自行推导业务含义

#### `GET /api/graph/nodes/{blog_id}/neighbors`

用途：基于当前节点返回邻域扩展结果，供图页“展开 1 跳 / 2 跳”使用。

查询参数：

- `hops`: 允许 `1` 或 `2`
- `limit`: 邻域节点上限

响应结构与 `GET /api/graph/views/core` 相同，但：

- `meta.strategy` 固定为 `neighborhood`
- `meta.focus_node_id` 为当前中心节点
- `meta.hops` 为实际展开跳数

#### `GET /api/graph/snapshots/latest`

用途：返回最新离线图快照 manifest。

响应结构：

```json
{
  "version": "20260331T000000000000Z",
  "generated_at": "2026-03-31T00:00:00+00:00",
  "source": "snapshot",
  "has_stable_positions": true,
  "total_nodes": 5306,
  "total_edges": 9758,
  "available_nodes": 5306,
  "available_edges": 9758,
  "graph_fingerprint": "4d9c...a1f3",
  "file": "graph-layout-20260331T000000000000Z.json"
}
```

说明：

- 这是对前端可见的受控发布边界，浏览器不应直接依赖 crawler 导出目录路径
- 若本地尚无快照文件，或底层 graph 数据已经变化，服务会先基于当前数据构建并落盘，再返回 manifest

#### `GET /api/graph/snapshots/{version}`

用途：返回指定版本的离线图快照。

响应结构与 `GET /api/graph/views/core` 类似，但包含完整 snapshot 范围的 `nodes` / `edges` 以及顶层 `version`、`generated_at`。

### 3.4 日志与搜索

#### `GET /api/logs`

用途：返回爬虫日志列表。

说明：

- 当前后端未暴露 `limit` 参数
- 实际数据来自 `persistence-api /internal/logs`
- 内部服务默认最多返回最近 `100` 条

#### `GET /api/search?q=...`

用途：按关键词搜索 blogs、edges、logs。

查询参数：

- `q`: 搜索关键词，必填

响应结构：

```json
{
  "query": "friend",
  "blogs": [],
  "edges": [],
  "logs": []
}
```

匹配规则：

- blog：匹配 `domain`、`url`、`normalized_url`
- edge：匹配 `link_url_raw`、`link_text`
- log：匹配 `message`

补充说明：

- 当 `q` 为空字符串时，返回空结果集
- 若本地搜索缓存为空，search 服务会回退到 persistence 快照进行查询
- 当前前端搜索页已直接消费该接口，并把 `blogs` 作为主结果区块展示

### 3.5 爬取执行接口

#### `POST /api/crawl/bootstrap`

用途：从 `seed.csv` 导入种子博客。

调用链：

- `backend` -> `crawler /internal/crawl/bootstrap`

响应字段：

- `seed_path`: 实际导入的种子文件路径
- `imported`: 新导入的 blog 数量

#### `POST /api/crawl/run`

用途：执行一次同步爬取批次。

查询参数：

- `max_nodes`: 可选，本次最多处理多少个 blog

调用链：

1. `backend` 调 `crawler /internal/crawl/run`
2. 执行成功后，`backend` 尝试调用 `search /internal/search/reindex`
3. 即使重建索引失败，也不会让本次 crawl 请求失败

典型响应：

```json
{
  "processed": 3,
  "discovered": 12,
  "failed": 0,
  "exports": {
    "nodes_csv": "...",
    "edges_csv": "...",
    "graph_json": "..."
  }
}
```

返回字段语义：

- `processed`: 本次实际处理的 blog 数
- `discovered`: 本次发现并入库的新链接总数
- `failed`: 本次处理失败的 blog 数
- `exports`: 导出文件信息

### 3.6 数据维护接口

#### `POST /api/database/reset`

用途：重置数据库中的 crawler 相关数据，便于测试和开发时快速回到初始状态。

行为说明：

- 仅允许在 crawler 运行器不处于 `starting/running/stopping` 时调用
- 若运行器忙碌，返回 `409`，错误详情为 `crawler_busy`
- 会清空 `blogs`、`edges`、`crawl_logs`
- backend 在数据库重置后会尝试调用 `search /internal/search/reindex`
- 即使 search 重建失败，数据库重置结果仍会返回，并附带 `search_reindexed=false`

成功响应示例：

```json
{
  "ok": true,
  "blogs_deleted": 12,
  "edges_deleted": 34,
  "logs_deleted": 56,
  "search_reindexed": true,
  "search": {
    "blogs": 0,
    "edges": 0,
    "logs": 0,
    "cache_path": "..."
  }
}
```

### 3.7 运行时控制接口

#### `GET /api/runtime/status`

用途：查看 crawler 运行时完整快照。

结构见“数据模型”中的 `RuntimeSnapshot`。

#### `GET /api/runtime/current`

用途：查看当前正在执行的 blog 简要信息。

相比 `/api/runtime/status`，字段更少，聚焦当前任务。

返回字段：

- `runner_status`
- `active_run_id`
- `current_blog_id`
- `current_url`
- `current_stage`
- `last_started_at`
- `last_error`

#### `POST /api/runtime/start`

用途：启动后台持续运行的 crawler 循环。

行为说明：

- 若当前已在 `starting/running/stopping`，直接返回当前快照
- 成功启动后会创建新的 `active_run_id`

#### `POST /api/runtime/stop`

用途：请求后台 crawler 在安全点停止。

行为说明：

- 若当前已是 `idle`，直接返回当前快照
- 否则将状态切到 `stopping`

#### `POST /api/runtime/run-batch`

用途：在运行器空闲时同步执行一批 crawl 任务。

请求体：

```json
{
  "max_nodes": 10
}
```

响应分两类：

1. 运行器忙碌时：

```json
{
  "accepted": false,
  "reason": "runtime_busy",
  "runtime": {}
}
```

2. 成功执行时：

```json
{
  "accepted": true,
  "mode": "batch",
  "result": {},
  "runtime": {}
}
```

补充说明：

- backend 在 batch 完成后也会尝试重建 search 索引
- search 重建失败不会影响主流程返回

## 4. 内部服务 API 详细说明

### 4.1 Crawler 服务

源码位置： [crawler/main.py](/Users/lige/code/HeyBlog/crawler/main.py)

基础信息：

- 服务名：`HeyBlog Crawler Service`
- 默认端口：`8010`

接口列表：

### `GET /internal/health`

返回：

```json
{
  "status": "ok"
}
```

### `POST /internal/crawl/bootstrap`

用途：导入种子数据。

实际执行：`CrawlPipeline.bootstrap_seeds()`

### `POST /internal/crawl/run`

用途：同步执行一次爬取。

查询参数：

- `max_nodes`: 可选

实际执行：`CrawlPipeline.run_once(max_nodes=max_nodes)`

### `GET /internal/runtime/status`

用途：返回运行时完整快照。

### `GET /internal/runtime/current`

用途：返回当前任务摘要。

### `POST /internal/runtime/start`

用途：启动后台循环。

### `POST /internal/runtime/stop`

用途：请求停止后台循环。

### `POST /internal/runtime/run-batch`

用途：执行同步 batch。

请求体：

```json
{
  "max_nodes": 10
}
```

### 4.2 Search 服务

源码位置： [search/main.py](/Users/lige/code/HeyBlog/search/main.py)

基础信息：

- 服务名：`HeyBlog Search Service`
- 默认端口：`8020`

接口列表：

### `GET /internal/health`

返回：

```json
{
  "status": "ok"
}
```

### `GET /internal/search?q=...`

用途：搜索缓存索引；缓存不存在或为空时回退到 persistence 快照。

查询参数：

- `q`: 搜索词

返回结构：

- `query`
- `blogs`
- `edges`
- `logs`

### `POST /internal/search/reindex`

用途：重建搜索缓存文件。

返回字段：

- `blogs`: 索引内 blog 数
- `edges`: 索引内 edge 数
- `logs`: 索引内 log 数
- `cache_path`: 索引缓存文件路径

### 4.3 Persistence API 服务

源码位置： [persistence_api/main.py](/Users/lige/code/HeyBlog/persistence_api/main.py)

基础信息：

- 服务名：`HeyBlog Persistence Service`
- 默认端口：`8030`

接口列表：

### `GET /internal/health`

返回：

```json
{
  "status": "ok"
}
```

### `GET /internal/blogs`

用途：返回全部 blog 记录。

### `GET /internal/queue/next?max_depth=...`

用途：取出下一个待处理 blog，并立即将其状态更新为 `PROCESSING`。

查询参数：

- `max_depth`: 最大抓取深度

行为说明：

- 只从 `crawl_status = 'WAITING'` 中选择
- 按 `depth ASC, id ASC` 排序
- 选中后立刻更新为 `PROCESSING`

### `GET /internal/blogs/{blog_id}`

用途：按 id 查询单个 blog。

### `POST /internal/blogs/upsert`

用途：插入 blog，若 `normalized_url` 已存在则直接返回已有 id。

请求体：

```json
{
  "url": "https://example.com/",
  "normalized_url": "https://example.com/",
  "domain": "example.com",
  "depth": 0,
  "source_blog_id": null
}
```

响应：

```json
{
  "id": 1,
  "inserted": true
}
```

### `POST /internal/blogs/{blog_id}/result`

用途：回写单个 blog 的抓取结果。

请求体：

```json
{
  "crawl_status": "FINISHED",
  "status_code": 200,
  "friend_links_count": 12
}
```

响应：

```json
{
  "ok": true
}
```

### `GET /internal/edges`

用途：返回全部边记录。

### `POST /internal/edges`

用途：插入一条边，若 `(from_blog_id, to_blog_id)` 已存在则忽略。

请求体：

```json
{
  "from_blog_id": 1,
  "to_blog_id": 2,
  "link_url_raw": "https://example.com/",
  "link_text": "友情链接"
}
```

响应：

```json
{
  "ok": true
}
```

### `GET /internal/logs?limit=100`

用途：返回最近日志，默认 `100` 条。

排序说明：

- 按 `id DESC`

### `POST /internal/logs`

用途：写入一条日志。

请求体：

```json
{
  "blog_id": 1,
  "stage": "crawl",
  "result": "success",
  "message": "Crawled https://example.com/"
}
```

响应：

```json
{
  "ok": true
}
```

### `GET /internal/stats`

用途：返回聚合统计。

返回字段：

- `total_blogs`
- `total_edges`
- `max_depth`
- `average_friend_links`
- `status_counts`
- `pending_tasks`
- `processing_tasks`
- `failed_tasks`
- `finished_tasks`

### `GET /internal/graph`

用途：返回完整图结构。

响应：

```json
{
  "nodes": [],
  "edges": []
}
```

### `GET /internal/graph/views/core`

用途：返回结构化初始子图。

查询参数与公共 `GET /api/graph/views/core` 一致。

### `GET /internal/graph/nodes/{blog_id}/neighbors`

用途：返回单节点邻域扩展结果。

### `GET /internal/graph/snapshots/latest`

用途：返回最新 snapshot manifest。

### `GET /internal/graph/snapshots/{version}`

用途：返回指定版本 snapshot payload。

### `GET /internal/search-snapshot`

用途：为 search 服务提供全量搜索快照。

响应：

```json
{
  "blogs": [],
  "edges": [],
  "logs": []
}
```

补充说明：

- 其中 logs 固定取最近 `500` 条

### `POST /internal/database/reset`

用途：重置 persistence 层中的 crawler 数据。

行为说明：

- 清空 `blogs`、`edges`、`crawl_logs`
- 重置 SQLite/PostgreSQL 的自增主键计数器

响应：

```json
{
  "ok": true,
  "blogs_deleted": 12,
  "edges_deleted": 34,
  "logs_deleted": 56
}
```

## 5. 数据模型整理

以下字段来自当前仓库实现与前端类型定义，适合作为现阶段统一理解口径。

### 5.1 BlogRecord

来源：

- [persistence_api/repository.py](/Users/lige/code/HeyBlog/persistence_api/repository.py)
- [frontend/src/lib/api.ts](/Users/lige/code/HeyBlog/frontend/src/lib/api.ts)

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `number` | blog 主键 |
| `url` | `string` | 原始 URL |
| `normalized_url` | `string` | 归一化 URL，唯一键 |
| `domain` | `string` | 域名 |
| `title` | `string \| null` | 站点主页解析出的 `<title>`，缺失时为 `null` |
| `icon_url` | `string \| null` | 站点标签页 icon URL；优先使用页面声明的 icon 链接，缺失时可能回退为 `${origin}/favicon.ico` |
| `status_code` | `number \| null` | 最近抓取 HTTP 状态码 |
| `crawl_status` | `string` | 当前抓取状态，常见值有 `WAITING` `PROCESSING` `FAILED` `FINISHED` |
| `friend_links_count` | `number` | 最近一次抓取发现的友链数 |
| `depth` | `number` | 图遍历深度 |
| `source_blog_id` | `number \| null` | 来源 blog id |
| `last_crawled_at` | `string \| null` | 最近抓取时间 |
| `created_at` | `string` | 创建时间 |
| `updated_at` | `string` | 更新时间 |

### 5.2 EdgeRecord

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `number` | edge 主键 |
| `from_blog_id` | `number` | 起点 blog id |
| `to_blog_id` | `number` | 终点 blog id |
| `link_url_raw` | `string` | 页面中抽取到的原始链接 |
| `link_text` | `string \| null` | 链接文本 |
| `discovered_at` | `string` | 发现时间 |

### 5.3 LogRecord

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `number` | 日志主键 |
| `blog_id` | `number \| null` | 关联 blog id |
| `stage` | `string` | 阶段，如 `bootstrap`、`crawl` |
| `result` | `string` | 结果，如 `success`、`error` |
| `message` | `string` | 文本消息 |
| `created_at` | `string` | 创建时间 |

### 5.4 RuntimeSnapshot

来源： [crawler/runtime.py](/Users/lige/code/HeyBlog/crawler/runtime.py)

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `runner_status` | `string` | 运行器状态，常见值有 `idle` `starting` `running` `stopping` `error` |
| `active_run_id` | `string \| null` | 当前运行 ID |
| `current_blog_id` | `number \| null` | 当前处理 blog id |
| `current_url` | `string \| null` | 当前处理 URL |
| `current_stage` | `string \| null` | 当前阶段，如 `crawling` `completed` `error` |
| `last_started_at` | `string \| null` | 最近启动时间 |
| `last_stopped_at` | `string \| null` | 最近停止时间 |
| `last_error` | `string \| null` | 最近错误 |
| `last_result` | `object \| null` | 最近执行结果 |

### 5.5 StatsPayload

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `total_blogs` | `number` | blog 总数 |
| `total_edges` | `number` | edge 总数 |
| `max_depth` | `number` | 最大深度 |
| `average_friend_links` | `number` | 平均友链数 |
| `status_counts` | `Record<string, number>` | 各状态计数 |
| `pending_tasks` | `number` | `WAITING` 数量 |
| `processing_tasks` | `number` | `PROCESSING` 数量 |
| `failed_tasks` | `number` | `FAILED` 数量 |
| `finished_tasks` | `number` | `FINISHED` 数量 |

## 6. 服务调用链

### 6.1 读接口调用链

- 前端 -> `backend /api/*`
- `backend` -> `persistence-api` 获取 blogs、edges、graph、stats、logs
- `backend` -> `search` 获取搜索结果
- `backend` -> `crawler` 获取运行时状态

### 6.2 写接口调用链

#### 种子导入

- 前端/调用方 -> `POST /api/crawl/bootstrap`
- `backend` -> `crawler /internal/crawl/bootstrap`
- `crawler` 读取 `seed.csv`
- `crawler` -> `persistence-api /internal/blogs/upsert`
- `crawler` -> `persistence-api /internal/logs`

#### 单次 crawl 运行

- 前端/调用方 -> `POST /api/crawl/run`
- `backend` -> `crawler /internal/crawl/run`
- `crawler` -> `persistence-api /internal/queue/next`
- `crawler` 抓取与解析页面
- `crawler` -> `persistence-api /internal/blogs/upsert`
- `crawler` -> `persistence-api /internal/edges`
- `crawler` -> `persistence-api /internal/blogs/{id}/result`
- `crawler` -> `persistence-api /internal/logs`
- `backend` -> `search /internal/search/reindex`（尽力而为）

#### 运行时 batch

- 前端/调用方 -> `POST /api/runtime/run-batch`
- `backend` -> `crawler /internal/runtime/run-batch`
- batch 完成后 `backend` 尝试触发 search reindex

## 7. 当前 API 观察与统筹建议

基于当前实现，现阶段可以先按下面的口径做统筹：

- 对外协议以 `backend /api/*` 为准，前端不要直接依赖内部服务接口
- 内部服务接口已经比较清晰，但目前没有统一版本号，也没有显式 OpenAPI schema 文档归档
- `/api/logs` 当前未向上暴露 `limit` 参数，如果后续日志量增加，建议补上
- `/api/crawl/run` 使用 query 参数 `max_nodes`，而 `/api/runtime/run-batch` 使用 JSON body `max_nodes`，风格不完全一致，后续可统一
- `search` 当前是轻量缓存式实现，属于可重建索引，不是强一致检索服务
- `services/*` 只是兼容入口，后续文档与新开发应优先引用顶层目录 `backend/`、`crawler/`、`search/`、`persistence_api/`

## 8. 主要源码索引

- 后端聚合服务： [backend/main.py](/Users/lige/code/HeyBlog/backend/main.py)
- 爬虫服务： [crawler/main.py](/Users/lige/code/HeyBlog/crawler/main.py)
- 运行时控制： [crawler/runtime.py](/Users/lige/code/HeyBlog/crawler/runtime.py)
- 爬虫主流程： [crawler/pipeline.py](/Users/lige/code/HeyBlog/crawler/pipeline.py)
- 搜索服务： [search/main.py](/Users/lige/code/HeyBlog/search/main.py)
- 持久化服务： [persistence_api/main.py](/Users/lige/code/HeyBlog/persistence_api/main.py)
- 仓储实现： [persistence_api/repository.py](/Users/lige/code/HeyBlog/persistence_api/repository.py)
- 数据库 schema： [persistence_api/schema.py](/Users/lige/code/HeyBlog/persistence_api/schema.py)
- 前端 API 类型： [frontend/src/lib/api.ts](/Users/lige/code/HeyBlog/frontend/src/lib/api.ts)
