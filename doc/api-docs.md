# HeyBlog API 文档

## 适合谁看

- 想确认公共 API 和内部 API 契约的开发者
- 准备新增、调整或核对 HTTP 路由与返回结构的读者

## 建议前置阅读

- [README](../readme.md)
- [项目结构说明](./project-structure.md)
- [服务调用架构](./service-architecture.md)

## 不包含什么

- 不重复讲目录和服务职责边界，那部分见 [project-structure.md](./project-structure.md) 与 [services-overview.md](./services-overview.md)
- 不展开所有环境变量，那部分见 [config-reference.md](./config-reference.md)

## 最后核对源码入口

- [backend/main.py](../backend/main.py)
- [crawler/main.py](../crawler/main.py)
- [search/main.py](../search/main.py)
- [persistence_api/main.py](../persistence_api/main.py)
- [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)

## 1. 文档目的

这份文档基于当前仓库源码整理 HeyBlog 已实现的 HTTP API，重点说明：

- 哪些是前端或外部调用方应该依赖的公共 API
- 哪些是拆分服务之间使用的内部 API
- 每个接口的请求参数、返回结构和职责边界
- 与接口直接相关的服务调用关系

当前代码实现对应的服务分层如下：

- `frontend`：public discovery surface + protected admin surface
- `backend`：统一对外 API 聚合层
- `crawler`：爬虫执行与运行时控制
- `search`：搜索索引与查询
- `persistence-api`：持久化读写接口
- `persistence-db`：PostgreSQL 数据库

配套文档：

- [project-structure.md](./project-structure.md)
- [services-overview.md](./services-overview.md)
- [service-architecture.md](./service-architecture.md)
- [config-reference.md](./config-reference.md)
- [developer-workflows.md](./developer-workflows.md)

默认端口来自 [docker-compose.yml](../docker-compose.yml)：

- `frontend`: `3000`
- `backend`: `8000`
- `crawler`: `8010`
- `search`: `8020`
- `persistence-api`: `8030`
- `persistence-db`: `5432`

## 2. API 分层总览

### 2.1 Public API

Public API 由 `backend` 服务统一暴露，供 public 浏览、搜索、图谱与 ingestion 流程使用：

- `GET /`
- `GET /internal/health`
- `GET /api/status`
- `GET /api/blogs`
- `GET /api/blogs/catalog`
- `GET /api/blogs/lookup`
- `GET /api/blogs/{blog_id}`
- `GET /api/edges`
- `GET /api/graph`
- `GET /api/graph/views/core`
- `GET /api/graph/nodes/{blog_id}/neighbors`
- `GET /api/graph/snapshots/latest`
- `GET /api/graph/snapshots/{version}`
- `GET /api/stats`
- `GET /api/logs`
- `GET /api/search`
- `GET /api/ingestion-requests`
- `POST /api/ingestion-requests`
- `GET /api/ingestion-requests/{request_id}`

源码位置： [backend/main.py](../backend/main.py)

补充说明：

- 浏览器实际访问的是 `frontend` 服务。
- [frontend/server.py](../frontend/server.py) 会把 `/api/*` 代理到 `backend`。
- 因此“公共 API 由 backend 提供”与“浏览器经 frontend 访问 API”这两件事同时成立。
- blog 规则重扫接口同样由 `frontend -> backend` 访问，但实际归并动作发生在 persistence 层。

### 2.2 Admin API

Admin API 同样由 `backend` 暴露，但统一位于 `/api/admin/*` 下，并要求 `Authorization: Bearer <HEYBLOG_ADMIN_TOKEN>`：

- `GET /api/admin/runtime/status`
- `GET /api/admin/runtime/current`
- `POST /api/admin/runtime/start`
- `POST /api/admin/runtime/stop`
- `POST /api/admin/runtime/run-batch`
- `POST /api/admin/crawl/bootstrap`
- `POST /api/admin/crawl/run`
- `POST /api/admin/database/reset`
- `GET /api/admin/blog-labeling/candidates`
- `GET /api/admin/blog-labeling/tags`
- `POST /api/admin/blog-labeling/tags`
- `GET /api/admin/blog-labeling/export`
- `PUT /api/admin/blog-labeling/labels/{blog_id}`
- `POST /api/admin/blog-dedup-scans`
- `GET /api/admin/blog-dedup-scans/latest`
- `GET /api/admin/blog-dedup-scans/{run_id}`
- `GET /api/admin/blog-dedup-scans/{run_id}/items`

认证语义：

- 未提供 token：`401 admin_auth_required`
- token 不合法：`403 admin_auth_invalid`
- 未配置 `HEYBLOG_ADMIN_TOKEN` 且未开启 `HEYBLOG_ADMIN_DEV_BYPASS=true`：`503 admin_auth_not_configured`

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
- `average_friend_links`
- `status_counts`
- `pending_tasks`
- `processing_tasks`
- `failed_tasks`
- `finished_tasks`

字段语义：

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
- 这是 legacy 全量接口。当前 Blog 概览页主路径已经迁移到 `GET /api/blogs/catalog`，但博客详情页仍会结合 `GET /api/blogs` 与 `GET /api/edges` 计算入边与邻居名称映射。

#### `GET /api/blogs/catalog`

用途：为“发现博客”入口提供分页、搜索、发现型筛选与排序。

查询参数：

- `page`: 页码，默认 `1`，最小值为 `1`
- `page_size`: 每页条数，默认 `50`，最终会被限制在 `1..200`
- `q`: 通用模糊搜索，匹配 `title` / `domain` / `url`
- `site`: 站点筛选，匹配 `title` / `domain`
- `url`: URL 筛选，匹配 `url` / `normalized_url`
- `status`: 抓取状态精确筛选；会先做 `trim + uppercase`，仅允许 `WAITING`、`PROCESSING`、`FINISHED`、`FAILED`
- `statuses`: 多状态筛选，逗号分隔；会对每个值做 `trim + uppercase`，仅允许 `WAITING`、`PROCESSING`、`FINISHED`、`FAILED`
- `sort`: 排序方式，允许 `id_asc`、`id_desc`、`recent_activity`、`connections`、`recently_discovered`
- `has_title`: 是否要求有标题；支持布尔值，也接受 `1/0`、`true/false`、`yes/no`
- `has_icon`: 是否要求有 icon；支持布尔值，也接受 `1/0`、`true/false`、`yes/no`
- `min_connections`: 最小连接度阈值，负数会被归一化为 `0`

归一化与排序规则：

- 空白字符串会被视为未传参
- 非法 `status` 返回 `422`
- 非法 `statuses` 返回 `422`
- 非法 `sort` 返回 `422`
- 当 `statuses` 存在时优先于 `status`，用于同时查询多个 `crawl_status`
- `has_title` / `has_icon` 仅在传入真值时启用过滤；传入假值会保留参数值但不额外筛掉空字段记录
- `id_asc` 按 `id ASC`
- `recent_activity` 按 `activity_at DESC, connection_count DESC, id DESC`
- `connections` 按 `connection_count DESC, activity_at DESC, id DESC`
- `recently_discovered` 按 `created_at DESC, id DESC`
- `id_desc` 按 `id DESC`
- 若请求页码超出最后一页且结果集非空，服务端会回退到最后一页，并在响应中返回实际生效页码

响应结构见“数据模型”章节中的 `BlogCatalogPageRecord`。

当前前端使用方式：

- 统一 discovery 主入口固定以 `statuses=WAITING,PROCESSING&sort=id_asc` 渲染“当前博客状态”板块
- 发现页只请求当前页，不再拉全量 blog 列表
- 该请求默认不做 5 秒轮询，也不依赖窗口聚焦自动刷新
- 发现页会利用新增字段直接渲染博客卡片的活跃度、连接度与身份完整度提示

#### `GET /api/blogs/lookup?url=...`

用途：对单个博客首页 URL 做数据库存在性判断，供统一 discovery 页的“检查博客 URL 是否已收录”区域使用。

查询参数：

- `url`: 博客首页 URL，必填

匹配阶梯：

- 先复用 ingestion 的 canonicalization / identity 规则，把输入归一化为 `normalized_query_url`
- 优先按 canonical homepage identity 精确匹配
- 若 identity 未命中，再回退到 `normalized_url` 精确相等匹配
- 若仍未命中，则返回空数组；当前不做 substring / domain contains 型广义搜索

响应结构：

```json
{
  "query_url": "https://alpha.example/",
  "normalized_query_url": "https://alpha.example/",
  "items": [],
  "total_matches": 0,
  "match_reason": null
}
```

补充说明：

- `match_reason` 当前固定为 `identity_key`、`normalized_url` 或 `null`
- 该接口是薄 lookup payload，不复用 catalog 的分页 envelope
- 统一 discovery 页的 lookup 状态会单独映射到 `lookup=` URL 参数，不与 queue 分页/排序参数混用

#### `GET /api/blogs/{blog_id}`

用途：返回单个 blog 详情，并追加该 blog 的双向关系聚合结果与粗糙推荐。

行为说明：

- 若 blog 不存在，返回 `404`
- 返回内容基于单 blog 记录扩展了 `incoming_edges` 与 `outgoing_edges`

额外字段：

- `incoming_edges`: 所有 `to_blog_id == blog_id` 的边，每条边额外携带 `neighbor_blog`
- `outgoing_edges`: 所有 `from_blog_id == blog_id` 的边，每条边额外携带 `neighbor_blog`
- `recommended_blogs`: “朋友的朋友”推荐列表，规则是“当前博客的友链认识、但当前博客还没直接认识的博客”

其中 `neighbor_blog` 是详情页使用的邻居摘要，字段为：

- `id`
- `domain`
- `title`
- `icon_url`

### 3.4 管理员博客人工标注台

#### `GET /api/admin/blog-labeling/candidates`

用途：返回博客人工标注台使用的候选列表。该接口固定只返回 `crawl_status == FINISHED` 的 blog，并把当前人工标签、多标签筛选元数据一起合并到响应里。

查询参数：

- `page`: 页码，默认 `1`
- `page_size`: 每页条数，默认 `50`，最终会被限制在 `1..200`
- `q`: 模糊搜索，匹配 `title` / `domain` / `url` / `normalized_url`
- `label`: 标签 `slug` 精确筛选，例如 `blog`、`official`、`government`
- `labeled`: 标注状态筛选；支持 `1/0`、`true/false`、`yes/no`
- `sort`: 排序方式，允许 `id_desc`、`recent_activity`、`recently_labeled`

响应结构：

- 复用 `BlogRecord` 的主体字段
- 追加 `labels`、`label_slugs`、`last_labeled_at`、`is_labeled`
- 顶层追加 `available_tags`，用于前端渲染可选标签与新建标签后的刷新
- 分页包装结构与 `GET /api/blogs/catalog` 一致

语义说明：

- 未标注状态通过 `labels = []` 与 `is_labeled = false` 表达，不把“未标注”落成特殊标签
- 一个 blog 可以同时拥有多个标签；`label` 查询参数表达“包含该标签”的筛选语义，而不是单值相等比较
- 该接口只服务于标注工作台，不改变现有发现页 `GET /api/blogs/catalog` 的协议

成功响应示例：

```json
{
  "items": [
    {
      "id": 12,
      "url": "https://alpha.example/",
      "normalized_url": "https://alpha.example/",
      "domain": "alpha.example",
      "title": "Alpha Blog",
      "crawl_status": "FINISHED",
      "labels": [
        {
          "id": 3,
          "name": "blog",
          "slug": "blog",
          "created_at": "2026-04-05T19:55:00+00:00",
          "updated_at": "2026-04-05T19:55:00+00:00",
          "labeled_at": "2026-04-05T20:01:00+00:00"
        },
        {
          "id": 4,
          "name": "official",
          "slug": "official",
          "created_at": "2026-04-05T19:56:00+00:00",
          "updated_at": "2026-04-05T19:56:00+00:00",
          "labeled_at": "2026-04-05T20:01:00+00:00"
        }
      ],
      "label_slugs": ["blog", "official"],
      "last_labeled_at": "2026-04-05T20:01:00+00:00",
      "is_labeled": true
    }
  ],
  "available_tags": [
    {
      "id": 3,
      "name": "blog",
      "slug": "blog",
      "created_at": "2026-04-05T19:55:00+00:00",
      "updated_at": "2026-04-05T19:55:00+00:00"
    },
    {
      "id": 4,
      "name": "official",
      "slug": "official",
      "created_at": "2026-04-05T19:56:00+00:00",
      "updated_at": "2026-04-05T19:56:00+00:00"
    }
  ],
  "page": 1,
  "page_size": 50,
  "total_items": 1,
  "total_pages": 1,
  "has_next": false,
  "has_prev": false,
  "filters": {
    "q": null,
    "label": "official",
    "labeled": true,
    "sort": "recently_labeled"
  },
  "sort": "recently_labeled"
}
```

#### `GET /api/admin/blog-labeling/tags`

用途：返回当前所有可用标签类型定义，供前端渲染和复用。

响应结构：

- 返回数组，每项包含 `id`、`name`、`slug`、`created_at`、`updated_at`
- 标签按 `name` 升序返回

#### `POST /api/admin/blog-labeling/tags`

用途：创建一个新的标签类型；前端可以直接创建 `blog`、`unknown`、`official`、`government` 等业务标签。

请求体：

```json
{
  "name": "government"
}
```

行为说明：

- 服务端会对 `name` 进行 trim，并生成稳定的 `slug`
- 若同 `slug` 已存在，返回已有标签记录，不重复创建
- 空白或非法名称返回 `422`

成功响应示例：

```json
{
  "id": 7,
  "name": "government",
  "slug": "government",
  "created_at": "2026-04-05T20:10:00+00:00",
  "updated_at": "2026-04-05T20:10:00+00:00"
}
```

#### `GET /api/admin/blog-labeling/export`

用途：导出训练模型所需的人工标注 CSV。

响应类型：

- `text/csv`

返回约束：

- 第一行为表头：`url,title,label`
- 只导出已有至少一个人工标签的 blog；未标注数据会直接跳过
- `label` 列直接写入标签文本，例如 `blog`、`official`，而不是内部 `id` 或 `slug`
- 一个 blog 绑定多个标签时，会按 `blog x label` 展平成多行
- `title` 允许为空；若当前 blog 没有标题，则该列输出空字符串

#### `PUT /api/admin/blog-labeling/labels/{blog_id}`

用途：替换单个已完成抓取 blog 的整组人工标签。

请求体：

```json
{
  "tag_ids": [3, 4]
}
```

行为说明：

- 请求体中的 `tag_ids` 是完整替换语义，而不是增量 patch
- 同一个 blog 可以同时拥有多个标签
- 传空数组表示“清空该 blog 当前所有标签”

错误语义：

- `404`: `blog_id` 不存在
- `409`: 目标 blog 不是 `FINISHED`，拒绝写入训练样本标签
- `422`: `tag_ids` 中存在不存在的标签，或请求体非法

成功响应示例：

```json
{
  "blog_id": 12,
  "labels": [
    {
      "id": 3,
      "name": "blog",
      "slug": "blog",
      "created_at": "2026-04-05T19:55:00+00:00",
      "updated_at": "2026-04-05T19:55:00+00:00",
      "labeled_at": "2026-04-05T20:12:00+00:00"
    },
    {
      "id": 4,
      "name": "official",
      "slug": "official",
      "created_at": "2026-04-05T19:56:00+00:00",
      "updated_at": "2026-04-05T19:56:00+00:00",
      "labeled_at": "2026-04-05T20:12:00+00:00"
    }
  ],
  "label_slugs": ["blog", "official"],
  "last_labeled_at": "2026-04-05T20:12:00+00:00",
  "is_labeled": true
}
```

`recommended_blogs` 的每个元素包含：

- `blog`: 推荐博客本身，结构沿用扩展后的 `BlogRecord`
- `reason`: 当前固定为 `mutual_connection`
- `mutual_connection_count`: 有多少个共同中间博客指向了这个推荐博客
- `via_blogs`: 中间博客摘要列表，字段与 `neighbor_blog` 相同

推荐策略说明：

- 只基于当前博客的出边做一层扩展
- 排除自己
- 排除已经与当前博客直接相连的博客
- 这是阶段 1 的可替换粗糙实现，目标是先提供可解释的发现入口，而不是最终推荐系统

前端现状：

- 当前博客详情页直接消费该接口作为主数据源
- 详情页不再额外请求 `GET /api/blogs` 与 `GET /api/edges`
- incoming/outgoing 关系、邻居名称映射和“朋友的朋友”推荐都由后端在该接口内聚合

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
    "snapshot_namespace": "legacy"
  }
}
```

说明：

- `nodes` 元素沿用 `BlogRecord`，并额外携带 `x`、`y`、`degree`、`incoming_count`、`outgoing_count`、`priority_score`、`component_id`
- 当 `has_stable_positions` 为 `true` 时，前端会优先使用这些坐标直接渲染，而不是首次实时跑力导布局
- 当 `sample_mode != off` 时，会返回可复现的随机子图视图，但该模式只是辅助开关，不是默认主路径
- 服务在返回前会检查底层 graph 是否已变化；若当前仓库数据与最新 snapshot 不一致，会先重建 snapshot，再返回最新视图
- `snapshot_namespace` 用于区分当前 view 依赖的 snapshot 来源；当前默认值为 `legacy`

#### `GET /api/graph/nodes/{blog_id}/neighbors`

用途：基于当前节点返回邻域扩展结果，供图页“展开 1 跳 / 2 跳”使用。

查询参数：

- `hops`: 允许 `1` 或 `2`
- `limit`: 邻域节点上限

响应结构与 `GET /api/graph/views/core` 相同，但：

- `meta.strategy` 固定为 `neighborhood`
- `meta.focus_node_id` 为当前中心节点
- `meta.hops` 为实际展开跳数

错误说明：

- 当目标 blog 不在当前已完成图谱快照中时，返回 `404 graph_node_not_found`

#### `GET /api/graph/snapshots/latest`

用途：返回最新离线图快照 manifest。

响应结构：

```json
{
  "version": "20260331T000000000000Z",
  "generated_at": "2026-03-31T00:00:00+00:00",
  "source": "snapshot",
  "snapshot_namespace": "legacy",
  "has_stable_positions": true,
  "total_nodes": 5306,
  "total_edges": 9758,
  "available_nodes": 5306,
  "available_edges": 9758,
  "graph_fingerprint": "4d9c...a1f3",
  "file": "graph-layout-20260331T000000000000Z.legacy.json"
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
- 当前实现不再把 crawl logs 持久化到数据库，因此该接口会返回空数组

#### `GET /api/search?q=...`

用途：按关键词搜索博客与关系线索。当前 public 主入口已经收敛到统一 discovery 页面，该接口主要保留给“高级关系线索搜索（兼容）”区域与旧 `/search?...kind=relations` 链接。

查询参数：

- `q`: 搜索关键词，必填
- `kind`: 搜索范围，允许 `all`、`blogs`、`relations`，默认 `all`
- `limit`: 返回上限，默认 `10`，最终会被限制在 `1..50`

响应结构：

```json
{
  "query": "friend",
  "kind": "all",
  "limit": 10,
  "blogs": [],
  "edges": [],
  "logs": []
}
```

匹配规则：

- blog：匹配 `title`、`domain`、`url`、`normalized_url`
- edge：匹配 `link_url_raw`、`link_text`，以及边两端博客的 `title` / `domain`
- log：当前固定为空数组，不参与命中

关系结果增强字段：

- 每条 `edge` 结果会额外带上 `from_blog` 与 `to_blog`
- 这两个字段都是博客摘要，字段为 `id`、`domain`、`title`、`icon_url`

补充说明：

- 当 `q` 为空字符串时，返回空结果集
- 非法 `kind` 返回 `422`
- 若本地搜索缓存为空，search 服务会回退到 persistence 快照进行查询
- `/search` 当前是 alias route：非 relations 查询会迁移为统一 discovery 页中的 `lookup` 语义，relations 查询仍在同页兼容区调用该接口

#### `GET /api/ingestion-requests`

用途：返回统一 discovery 页“优先处理博客清单”所需的公开优先录入请求列表。

返回约束：

- 固定最多返回 `20` 条
- inclusion rule: 先返回 active request（`QUEUED`、`CRAWLING_SEED`），再补最近创建的 terminal request，直到达到上限
- 排序固定为 `active-first -> created_at DESC -> request_id DESC`

公开字段：

- `request_id`
- `requested_url`
- `normalized_url`
- `status`
- `seed_blog_id`
- `matched_blog_id`
- `blog_id`
- `error_message`
- `created_at`
- `updated_at`
- `blog`

隐私边界：

- 该公开列表不会返回 `email`
- 该公开列表不会返回 `request_token`

补充说明：

- `blog` 是裁剪后的公开摘要，至少包含 `id`、`url`、`domain`、`title`、`icon_url`、`crawl_status`
- 该列表接口服务统一页的优先队列面板，不替代单条状态查询接口

#### `POST /api/ingestion-requests`

用途：当搜索未命中时，由最终用户提交博客首页 URL 与联系邮箱，触发优先录入请求。

请求体：

```json
{
  "homepage_url": "https://example.com/",
  "email": "owner@example.com"
}
```

响应分两类：

- 已收录时：直接返回 `DEDUPED_EXISTING` 与现有 `blog_id`
- 未收录时：返回请求状态、`request_id`、`request_token`、seed blog 关联信息

补充说明：

- 后端会先做 URL normalize 与 email 基础校验
- 当前去重主键已经扩展为 `identity_key`；它会忽略 `http/https`、主页默认首页路径、`www.`，以及白名单博客别名子域（如 `blog.`）
- 活跃请求会按 `identity_key + ACTIVE_INGESTION_REQUEST_STATUSES` 复用，而不是重复创建 crawl
- `request_token` 是无账号体系下查询请求状态所需的轻量凭证

#### `GET /api/ingestion-requests/{request_id}?request_token=...`

用途：查询某个自助录入请求的当前状态。

当前返回字段重点包括：

- `status`: 当前请求状态，常见值有 `QUEUED`、`CRAWLING_SEED`、`COMPLETED`、`FAILED`
- `seed_blog_id`: 当前请求绑定的 seed blog
- `matched_blog_id`: 若已完成并命中 blog，则返回该 blog id
- `blog`: 当前关联 blog 的摘要信息
- `request_token`: 创建请求时返回的状态查询 token

补充说明：

- 当前首版未引入账号系统，因此状态查询依赖 `request_id + request_token`
- 若 `request_token` 不匹配，返回 `404`
- 统一 discovery 页的公开优先队列列表不会暴露该 `request_token`；只有创建者通过该单条接口查询时才会使用它

### 3.5 管理员爬取执行接口

#### `POST /api/admin/crawl/bootstrap`

用途：从 `seed.csv` 导入种子博客。

调用链：

- `backend` -> `crawler /internal/crawl/bootstrap`

响应字段：

- `seed_path`: 实际导入的种子文件路径
- `imported`: 新导入的 blog 数量

#### `POST /api/admin/crawl/run`

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

#### `POST /api/admin/blog-dedup-scans`

用途：管理员手动触发一次基于当前 `UrlDecisionChain` 的全库已收录 blog URL 重评估扫描。

行为说明：

- backend 会先读取 crawler runtime；若扫描前 crawler 正在运行，则先停爬并等待 `idle`
- 扫描期间 backend 会打开 `maintenance_in_progress` 维护锁
- `POST` 请求现在只负责创建一个 `RUNNING` scan run 并启动后台任务，因此前端会立刻收到可轮询的 run 摘要
- 维护窗口内新的 `POST /api/admin/runtime/start` 与 `POST /api/admin/runtime/run-batch` 会返回 `409 maintenance_in_progress`
- 当前实现会复用 crawler 的共享 `UrlDecisionChain` builder，对数据库里已存的 `blogs.url` 重新跑一遍完整 URL 过滤逻辑
- 被当前决策链拒绝的 blog 会连同其相关 edge 一起删除，并清空相关 ingestion 引用，避免残留悬挂关系
- 扫描 summary 中的 `total_count / scanned_count / kept_count / removed_count` 对应的是已存 blog URL 数量
- 扫描成功后 backend 会尝试调用 search reindex
- 若扫描前 crawler 原本在运行，backend 会在结束后尝试恢复 crawler，并把恢复结果写回 run summary
- 前端可通过 `GET /api/admin/blog-dedup-scans/latest` 或 `GET /api/admin/blog-dedup-scans/{run_id}` 轮询实时进度，其中 `scanned_count / total_count` 表示“已扫描 URL / 总共 URL”

返回字段重点包括：

- `id`
- `status`
- `ruleset_version`
- `total_count`
- `scanned_count`
- `removed_count`
- `kept_count`
- `crawler_was_running`
- `crawler_restart_attempted`
- `crawler_restart_succeeded`
- `search_reindexed`
- `error_message`
- `started_at` / `completed_at` / `duration_ms`

#### `GET /api/admin/blog-dedup-scans/latest`

用途：返回最近一次扫描摘要。

#### `GET /api/admin/blog-dedup-scans/{run_id}`

用途：返回指定扫描 run 的摘要。

#### `GET /api/admin/blog-dedup-scans/{run_id}/items`

用途：返回该次扫描中被决策链移除的 blog 明细与原因。

每条 item 至少包含：

- `survivor_blog_id`
  当前通常为 `null`；历史字段名保留用于兼容
- `removed_blog_id`
  当前表示被规则重扫移除的 blog id
- `survivor_identity_key`
  当前承载被扫描 blog 的 identity key 供排查使用
- `removed_url`
- `reason_code`
- `reason_codes`
- `survivor_selection_basis`
  当前承载 scanned blog id 与 decision score 等辅助调试信息

#### `POST /api/admin/database/reset`

用途：重置数据库中的 crawler 相关数据，便于测试和开发时快速回到初始状态。

行为说明：

- 仅允许在 crawler 运行器不处于 `starting/running/stopping` 时调用
- 若运行器忙碌，返回 `409`，错误详情为 `crawler_busy`
- 会清空 `blogs`、`edges`
- backend 在数据库重置后会尝试调用 `search /internal/search/reindex`
- 即使 search 重建失败，数据库重置结果仍会返回，并附带 `search_reindexed=false`

成功响应示例：

```json
{
  "ok": true,
  "blogs_deleted": 12,
  "edges_deleted": 34,
  "logs_deleted": 0,
  "search_reindexed": true,
  "search": {
    "blogs": 0,
    "edges": 0,
    "logs": 0,
    "cache_path": "..."
  }
}
```

### 3.7 管理员运行时控制接口

#### `GET /api/admin/runtime/status`

用途：查看 crawler 运行时完整快照。

结构见“数据模型”中的 `RuntimeSnapshot`。

补充字段：

- `maintenance_in_progress`: backend 当前是否处于管理员维护窗口；为 `true` 时新的 runtime 启动与批处理请求会被拒绝

#### `GET /api/admin/runtime/current`

用途：查看当前正在执行的 blog 简要信息。

相比 `/api/admin/runtime/status`，它仍聚焦“当前任务”，但现在会保留 worker 视角的摘要，方便 UI 直接渲染当前活跃 worker 列表。

返回字段：

- `runner_status`
- `active_run_id`
- `worker_count`
- `active_workers`
- `current_worker_id`
- `current_blog_id`
- `current_url`
- `current_stage`
- `task_started_at`
- `elapsed_seconds`
- `last_started_at`
- `last_stopped_at`
- `last_error`
- `last_result`
- `workers`

#### `POST /api/admin/runtime/start`

用途：启动后台持续运行的 crawler 循环。

行为说明：

- 若当前已在 `starting/running/stopping`，直接返回当前快照
- 成功启动后会创建新的 `active_run_id`
- 若 backend 当前处于 blog dedup 维护窗口，返回 `409 maintenance_in_progress`

#### `POST /api/admin/runtime/stop`

用途：请求后台 crawler 在安全点停止。

行为说明：

- 若当前已是 `idle`，直接返回当前快照
- 否则将状态切到 `stopping`

#### `POST /api/admin/runtime/run-batch`

用途：在运行器空闲时同步执行一批 crawl 任务。

补充说明：

- 若 backend 当前处于 blog dedup 维护窗口，返回 `409 maintenance_in_progress`

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

源码位置： [crawler/main.py](../crawler/main.py)

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

源码位置： [search/main.py](../search/main.py)

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
- `kind`
- `limit`
- `blogs`
- `edges`
- `logs`

补充说明：

- `kind` 的合法值为 `all`、`blogs`、`relations`
- `edges` 结果会附带 `from_blog` 与 `to_blog` 摘要，便于上游直接渲染关系线索

### `POST /internal/search/reindex`

用途：重建搜索缓存文件。

返回字段：

- `blogs`: 索引内 blog 数
- `edges`: 索引内 edge 数
- `logs`: 索引内 log 数
- `cache_path`: 索引缓存文件路径

### 4.3 Persistence API 服务

源码位置： [persistence_api/main.py](../persistence_api/main.py)

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

补充说明：

- 当前 `BlogRecord` 已包含可空的 `email` 字段，用于记录博主在自助优先录入时留下的联系邮箱
- 当前 `BlogRecord` 同时包含 `identity_key`、`identity_reason_codes` 与 `identity_ruleset_version`

### `GET /internal/blogs/catalog`

用途：为 backend 提供分页 blog catalog 查询。

查询参数与返回 envelope 与 `GET /api/blogs/catalog` 一致。

补充说明：

- 归一化逻辑在 persistence 层统一处理，SQLite 与 PostgreSQL 共享同一套分页/筛选规则
- 支持 `sort`、`has_title`、`has_icon`、`min_connections` 等发现型参数
- 支持 `statuses` 多状态过滤与 `id_asc` 排序，供统一 discovery 队列视图使用
- blog 行数据会直接带上连接度、活跃度和身份完整度等派生字段

### `GET /internal/blogs/lookup?url=...`

用途：为 backend 提供数据库权威的博客 URL 存在性查询。

补充说明：

- 返回薄 lookup payload，而不是 catalog 分页 envelope
- 命中顺序固定为 `identity_key -> normalized_url -> empty`
- `match_reason` 只允许 `identity_key`、`normalized_url` 或 `null`

### `GET /internal/queue/next`

用途：取出下一个待处理 blog，并立即将其状态更新为 `PROCESSING`。

行为说明：

- 只从 `crawl_status = 'WAITING'` 中选择
- 默认允许包含 priority seed；也可以通过 `include_priority=false` 只领取普通队列
- 选中后立刻更新为 `PROCESSING`

### `GET /internal/queue/priority-next`

用途：只领取由 `ingestion_requests` 驱动的高优先级 seed blog。

行为说明：

- 仅选择仍处于 `QUEUED` 的请求对应 seed
- 按 `priority DESC, created_at ASC, blog.id ASC` 领取
- 选中后立刻把 blog 更新为 `PROCESSING`

### `GET /internal/blogs/{blog_id}`

用途：按 id 查询单个 blog。

### `GET /internal/blogs/{blog_id}/detail`

用途：按 id 查询单个 blog，并聚合详情页所需的 `incoming_edges` / `outgoing_edges` 与邻居摘要。

### `POST /internal/blogs/upsert`

用途：插入 blog，若 `normalized_url` 已存在则直接返回已有 id。

请求体：

```json
{
  "url": "https://example.com/",
  "normalized_url": "https://example.com/",
  "domain": "example.com",
  "email": "owner@example.com"
}
```

其中 `email` 为可选字段。

响应：

```json
{
  "id": 1,
  "inserted": true
}
```

补充说明：

- repository 会优先按 `normalized_url` 与 `identity_key` 复用已有 blog。
- 对满足“tenant-like homepage 子域”启发式的 URL，入库时会直接把 blog URL / `normalized_url` 规范化为 registrable root 的 canonical URL；例如 `zhuruilei.66law.cn` 会收敛为 `https://66law.cn/`。像 `*.github.io`、`*.gitee.io` 这类显式排除的共享托管域名不受该规则影响。

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

- 当前实现固定返回空数组

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

补充说明：

- 当前只支持 `1` 或 `2` 跳扩展
- 当目标 blog 不在当前已完成图谱快照中时，返回 `404 graph_node_not_found`

### `GET /internal/graph/snapshots/latest`

用途：返回最新 snapshot manifest。

### `GET /internal/graph/snapshots/{version}`

用途：返回指定版本 snapshot payload。

### `GET /internal/graph/status`

用途：返回当前 persistence 图读后端的 readiness 信息，用于 rollout、shadow parity 与故障排查。

响应示例：

```json
{
  "graph_backend": "legacy",
  "configured_graph_backend": "age",
  "age_enabled": false,
  "age_sync_state": "not_configured",
  "parity_status": "unknown",
  "latest_snapshot_namespace": "legacy",
  "latest_snapshot_manifest": "graph-layout-latest.legacy.json",
  "age_graph_name": "heyblog_graph",
  "last_error": null
}
```

说明：

- `graph_backend` 表示当前真正对外提供 graph read 的后端；当前 rollout 默认仍为 `legacy`
- `configured_graph_backend` 表示配置层声明的目标后端；在 shadow 阶段它可以与 `graph_backend` 不同

### `POST /internal/graph/shadow/rebuild`

用途：显式触发 AGE shadow graph 重建。该动作与普通 graph read 解耦，不会在 `/internal/graph/views/core` 或邻域读取时隐式触发。

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

- 其中 `logs` 固定为空数组，用于保持 search 快照结构兼容

### `POST /internal/database/reset`

用途：重置 persistence 层中的 crawler 数据。

行为说明：

- 清空 `blogs`、`edges`
- `logs_deleted` 固定返回 `0`
- 重置主键计数器

响应：

```json
{
  "ok": true,
  "blogs_deleted": 12,
  "edges_deleted": 34,
  "logs_deleted": 0
}
```

补充说明：

- 若该 blog 是某个活跃 `ingestion_request` 的 seed，写回结果时会同步推进请求状态为 `COMPLETED` 或 `FAILED`

### `POST /internal/ingestion-requests`

用途：创建或复用一个用户自助优先录入请求。

请求体：

```json
{
  "homepage_url": "https://example.com/",
  "email": "owner@example.com"
}
```

返回：

- 已收录时：`DEDUPED_EXISTING`
- 新建或复用请求时：请求 payload，包含 `request_id`、`request_token`、`status`、`seed_blog_id`

补充说明：

- 去重与复用当前按 `identity_key` 执行，而不再只看 `normalized_url`
- 返回 payload 会附带 `identity_key`、`identity_reason_codes` 与 `identity_ruleset_version`
- 对满足“tenant-like homepage 子域”启发式的 URL，`normalized_url` 与 seed blog URL 会直接收敛到 registrable root 的 canonical URL；例如 `*.66law.cn` 会统一收敛到 `https://66law.cn/`。`*.github.io`、`*.gitee.io` 等显式排除域名不会被这样归并。

### `GET /internal/ingestion-requests/{request_id}`

用途：通过 `request_id + request_token` 查询请求状态。

查询参数：

- `request_token`: 创建请求时生成的查询 token

### `GET /internal/ingestion-requests`

用途：为 backend 提供统一 discovery 页“优先处理博客清单”所需的公开优先录入请求列表。

补充说明：

- 返回范围、排序与公开字段约束与 `GET /api/ingestion-requests` 一致
- internal/public 两层都不会在该列表 payload 中暴露 `email` 与 `request_token`

### `POST /internal/ingestion-requests/by-blog/{blog_id}/crawling`

用途：当 crawler 真正开始处理某个 seed blog 时，把关联请求推进到 `CRAWLING_SEED`。

### `POST /internal/blog-dedup-scans`

用途：同步执行一次基于当前共享 `UrlDecisionChain` 的 persistence 侧全库 blog URL 规则重扫；主要保留给内部测试与兼容调用。

查询参数：

- `crawler_was_running`: backend 透传的预扫描 runtime 状态

### `POST /internal/blog-dedup-scans/runs`

用途：创建一个 `RUNNING` 的规则重扫 run，并立即返回初始摘要，供 backend 异步编排使用。

查询参数：

- `crawler_was_running`: backend 透传的预扫描 runtime 状态

### `POST /internal/blog-dedup-scans/{run_id}/execute`

用途：执行指定 run 的 persistence 侧规则重扫逻辑，并在执行过程中持续更新 `total_count`、`scanned_count`、`removed_count`、`kept_count`。
当前四个计数字段都以已存 blog URL 数为口径。

### `POST /internal/blog-dedup-scans/{run_id}/finalize`

用途：由 backend 在扫描编排完成后回写 crawler 恢复和 search reindex 结果。

### `GET /internal/blog-dedup-scans/latest`

用途：返回最近一次 run summary。

### `GET /internal/blog-dedup-scans/{run_id}`

用途：返回指定 run summary。

### `GET /internal/blog-dedup-scans/{run_id}/items`

用途：返回指定 run 中被决策链移除的 blog 明细。

## 5. 数据模型整理

以下字段来自当前仓库实现与前端类型定义，适合作为现阶段统一理解口径。

### 5.1 BlogRecord

来源：

- [persistence_api/repository.py](persistence_api/repository.py)
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts)

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `number` | blog 主键 |
| `url` | `string` | 原始 URL |
| `normalized_url` | `string` | 归一化 URL，用于抓取与展示 |
| `identity_key` | `string` | blog 身份键，例如 `site:langhai.cc/` |
| `identity_reason_codes` | `string[]` | 当前 identity 解析命中的原因码 |
| `identity_ruleset_version` | `string` | 解析该 identity 时使用的规则版本 |
| `domain` | `string` | 域名 |
| `email` | `string \| null` | 博主联系邮箱；仅在用户自助优先录入时写入，默认 `null` |
| `title` | `string \| null` | 站点主页解析出的 `<title>`，缺失时为 `null` |
| `icon_url` | `string \| null` | 站点标签页 icon URL；优先使用页面声明的 icon 链接，缺失时可能回退为 `${origin}/favicon.ico` |
| `status_code` | `number \| null` | 最近抓取 HTTP 状态码 |
| `crawl_status` | `string` | 当前抓取状态，常见值有 `WAITING` `PROCESSING` `FAILED` `FINISHED` |
| `friend_links_count` | `number` | 最近一次抓取发现的友链数 |
| `last_crawled_at` | `string \| null` | 最近抓取时间 |
| `created_at` | `string` | 创建时间 |
| `updated_at` | `string` | 更新时间 |
| `incoming_count` | `number` | 指向该博客的边数 |
| `outgoing_count` | `number` | 该博客指向外部的边数 |
| `connection_count` | `number` | `incoming_count + outgoing_count` |
| `activity_at` | `string \| null` | 用于发现排序的活跃时间，优先取 `last_crawled_at`，否则回退到 `updated_at` |
| `identity_complete` | `boolean` | 当前是否同时具备非空 `title` 与 `icon_url` |

### 5.2 BlogCatalogPageRecord

来源：

- [persistence_api/repository.py](persistence_api/repository.py)
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts)

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `items` | `BlogRecord[]` | 当前页 blog 列表 |
| `page` | `number` | 当前实际页码；超出范围时可能回退到最后一页 |
| `page_size` | `number` | 当前实际每页大小 |
| `total_items` | `number` | 满足筛选条件的总记录数 |
| `total_pages` | `number` | 总页数；无结果时为 `0` |
| `has_next` | `boolean` | 是否存在下一页 |
| `has_prev` | `boolean` | 是否存在上一页 |
| `filters.q` | `string \| null` | 通用搜索关键词，匹配 `title` / `domain` / `url` |
| `filters.site` | `string \| null` | 站点筛选关键词，匹配 `title` / `domain` |
| `filters.url` | `string \| null` | URL 筛选关键词，匹配 `url` / `normalized_url` |
| `filters.status` | `string \| null` | 状态筛选值 |
| `filters.sort` | `string` | 当前生效排序 |
| `filters.has_title` | `boolean \| null` | 是否要求存在标题 |
| `filters.has_icon` | `boolean \| null` | 是否要求存在 icon |
| `filters.min_connections` | `number` | 最小连接度阈值 |
| `sort` | `string` | 当前生效排序；与 `filters.sort` 保持一致 |

### 5.3 IngestionRequestPayload

来源：

- [persistence_api/repository.py](persistence_api/repository.py)
- [frontend/src/lib/api.ts](frontend/src/lib/api.ts)

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` / `request_id` | `number` | 请求主键 |
| `requested_url` | `string` | 用户提交的原始首页 URL |
| `normalized_url` | `string` | 归一化后的 URL |
| `identity_key` | `string` | 当前请求命中的 blog 身份键 |
| `identity_reason_codes` | `string[]` | 当前 identity 解析原因码 |
| `identity_ruleset_version` | `string` | 当前 identity 规则版本 |
| `email` | `string` | 用户提交的联系邮箱 |
| `status` | `string` | 请求状态 |
| `priority` | `number` | 当前固定优先级值 |
| `seed_blog_id` | `number \| null` | 绑定的 seed blog |
| `matched_blog_id` | `number \| null` | 已完成时关联的最终 blog |
| `blog_id` | `number \| null` | 便于前端跳转的当前关联 blog id |
| `request_token` | `string` | 无账号状态查询 token |
| `seed_blog` | `BlogRecord \| null` | seed blog 摘要 |
| `matched_blog` | `BlogRecord \| null` | 已匹配 blog 摘要 |
| `blog` | `BlogRecord \| null` | 前端使用的当前 blog 视图 |
| `error_message` | `string \| null` | 失败时的错误摘要 |
| `created_at` / `updated_at` | `string` | 请求创建/更新时间 |

### 5.4 BlogDetailPayload

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `...BlogRecord` | `BlogRecord` | 详情页主博客信息 |
| `incoming_edges` | `BlogRelationRecord[]` | 指向当前博客的关系列表 |
| `outgoing_edges` | `BlogRelationRecord[]` | 当前博客指向外部的关系列表 |
| `recommended_blogs` | `BlogRecommendationRecord[]` | “朋友的朋友”推荐列表 |

其中：

- `BlogRelationRecord = EdgeRecord + { neighbor_blog: BlogNeighborSummary \| null }`
- `BlogRecommendationRecord = { blog, reason, mutual_connection_count, via_blogs }`
- `BlogNeighborSummary` 字段为 `id`、`domain`、`title`、`icon_url`

### 5.4 EdgeRecord

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `number` | edge 主键 |
| `from_blog_id` | `number` | 起点 blog id |
| `to_blog_id` | `number` | 终点 blog id |
| `link_url_raw` | `string` | 页面中抽取到的原始链接 |
| `link_text` | `string \| null` | 链接文本 |
| `discovered_at` | `string` | 发现时间 |

### 5.5 SearchPayload

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `query` | `string` | 原始查询词 |
| `kind` | `"all" \| "blogs" \| "relations"` | 当前搜索范围 |
| `limit` | `number` | 当前生效返回上限 |
| `blogs` | `BlogRecord[]` | 博客搜索结果 |
| `edges` | `SearchEdgeRecord[]` | 关系搜索结果 |
| `logs` | `LogRecord[]` | 当前恒为空数组 |

其中 `SearchEdgeRecord = EdgeRecord + { from_blog: BlogNeighborSummary \| null, to_blog: BlogNeighborSummary \| null }`。

### 5.6 RuntimeSnapshot

来源： [crawler/contracts/runtime.py](../crawler/contracts/runtime.py) 与 [crawler/runtime/service.py](../crawler/runtime/service.py)

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `runner_status` | `string` | 运行器状态，常见值有 `idle` `starting` `running` `stopping` `error` |
| `maintenance_in_progress` | `boolean \| null` | backend 维护锁状态；存在且为 `true` 时表示管理员规则重扫正在进行 |
| `active_run_id` | `string \| null` | 当前运行 ID |
| `worker_count` | `number` | 当前 runtime 配置的 worker 数量 |
| `active_workers` | `number` | 当前仍持有 blog 任务、尚未完成收尾的 worker 数量；在 `stopping` 期间也会计入 |
| `current_worker_id` | `string \| null` | 当前代表 worker 标识，优先选择活跃 worker |
| `current_blog_id` | `number \| null` | 当前处理 blog id |
| `current_url` | `string \| null` | 当前处理 URL |
| `current_stage` | `string \| null` | 当前阶段，如 `crawling` `completed` `error` |
| `task_started_at` | `string \| null` | 当前代表 worker 的任务开始时间 |
| `elapsed_seconds` | `number \| null` | 当前代表 worker 的任务已耗时秒数 |
| `last_started_at` | `string \| null` | 最近启动时间 |
| `last_stopped_at` | `string \| null` | 最近停止时间 |
| `last_error` | `string \| null` | 最近错误 |
| `last_result` | `object \| null` | 最近执行结果 |
| `workers` | `RuntimeWorkerSnapshot[]` | 各 worker 的运行快照列表 |

### 5.7 RuntimeWorkerSnapshot

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `worker_id` | `string` | worker 标识，如 `worker-1` |
| `worker_index` | `number` | worker 序号，1-based |
| `status` | `string` | worker 状态，如 `idle` `waiting` `running` `completed` `error` `stopping` |
| `current_blog_id` | `number \| null` | 当前处理 blog id |
| `current_url` | `string \| null` | 当前处理 URL |
| `current_stage` | `string \| null` | 当前阶段，如 `crawling` `completed` `waiting_for_work` |
| `task_started_at` | `string \| null` | 当前任务开始时间 |
| `last_transition_at` | `string \| null` | 最近一次状态迁移时间 |
| `last_completed_at` | `string \| null` | 最近一次完成时间 |
| `last_error` | `string \| null` | 最近错误 |
| `processed` | `number` | 当前 run 内已处理 blog 数 |
| `discovered` | `number` | 当前 run 内已发现 blog 数 |
| `failed` | `number` | 当前 run 内失败 blog 数 |
| `elapsed_seconds` | `number \| null` | 当前任务已耗时秒数；worker 空闲时为 `null` |

### 5.8 StatsPayload

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `total_blogs` | `number` | blog 总数 |
| `total_edges` | `number` | edge 总数 |
| `average_friend_links` | `number` | 平均友链数 |
| `status_counts` | `Record<string, number>` | 各状态计数 |
| `pending_tasks` | `number` | `WAITING` 数量 |
| `processing_tasks` | `number` | `PROCESSING` 数量 |
| `failed_tasks` | `number` | `FAILED` 数量 |
| `finished_tasks` | `number` | `FINISHED` 数量 |

## 6. 服务调用链

### 6.1 读接口调用链

- 前端 -> `backend /api/*`
- `backend` -> `persistence-api` 获取 blogs、blog detail、edges、graph、stats、logs
- `backend` -> `search` 获取搜索结果
- `backend` -> `crawler` 获取运行时状态

### 6.2 写接口调用链

#### 种子导入

- 管理员前端/调用方 -> `POST /api/admin/crawl/bootstrap`
- `backend` -> `crawler /internal/crawl/bootstrap`
- `crawler` 读取 `seed.csv`
- `crawler` -> `persistence-api /internal/blogs/upsert`
- `crawler` -> 结构化日志管线

#### 单次 crawl 运行

- 管理员前端/调用方 -> `POST /api/admin/crawl/run`
- `backend` -> `crawler /internal/crawl/run`
- `crawler` -> `persistence-api /internal/queue/next`
- `crawler` 抓取与解析页面
- `crawler` -> `persistence-api /internal/blogs/upsert`
- `crawler` -> `persistence-api /internal/edges`
- `crawler` -> `persistence-api /internal/blogs/{id}/result`
- `crawler` -> 结构化日志管线
- `backend` -> `search /internal/search/reindex`（尽力而为）

#### 运行时 batch

- 管理员前端/调用方 -> `POST /api/admin/runtime/run-batch`
- `backend` -> `crawler /internal/runtime/run-batch`
- batch 完成后 `backend` 尝试触发 search reindex

## 7. 当前 API 观察与统筹建议

基于当前实现，现阶段可以先按下面的口径做统筹：

- 对外协议以 `backend /api/*` 为准，前端不要直接依赖内部服务接口
- 内部服务接口已经比较清晰，但目前没有统一版本号，也没有显式 OpenAPI schema 文档归档
- `/api/logs` 当前未向上暴露 `limit` 参数，如果后续日志量增加，建议补上
- `/api/admin/crawl/run` 使用 query 参数 `max_nodes`，而 `/api/admin/runtime/run-batch` 使用 JSON body `max_nodes`，风格不完全一致，后续可统一
- `search` 当前是轻量缓存式实现，属于可重建索引，不是强一致检索服务
- `services/*` 只是兼容入口，后续文档与新开发应优先引用顶层目录 `backend/`、`crawler/`、`search/`、`persistence_api/`

## 8. 主要源码索引

- 后端聚合服务： [backend/main.py](../backend/main.py)
- 爬虫服务： [crawler/main.py](../crawler/main.py)
- 运行时控制： [crawler/runtime/service.py](../crawler/runtime/service.py)
- 爬虫主流程： [crawler/crawling/pipeline.py](../crawler/crawling/pipeline.py)
- 搜索服务： [search/main.py](../search/main.py)
- 持久化服务： [persistence_api/main.py](../persistence_api/main.py)
- 仓储实现： [persistence_api/repository.py](../persistence_api/repository.py)
- 数据库 schema： [persistence_api/schema.py](../persistence_api/schema.py)
- 前端 API 类型： [frontend/src/lib/api.ts](../frontend/src/lib/api.ts)
