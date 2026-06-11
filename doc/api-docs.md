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

Public API 由 `backend` 服务统一暴露，供 public 浏览、图谱与用户 seed 提交流程使用：

- `GET /`
- `GET /internal/health`
- `GET /api/status`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/email/verify/request`
- `POST /api/auth/email/verify/confirm`
- `POST /api/auth/password/forgot`
- `POST /api/auth/password/reset`
- `GET /api/me/label-selections`
- `GET /api/blogs/catalog`
- `POST /api/recommendations/random-blog-batches`
- `POST /api/recommendation-events`
- `GET /api/blogs/{blog_id}/stats`
- `POST /api/blogs/user-seeds`
- `POST /api/blogs/{blog_id}/user-labels`
- `GET /api/blogs/lookup`
- `GET /api/blogs/{blog_id}`
- `GET /api/icons/proxy`
- `GET /api/graph/views/core`
- `GET /api/graph/nodes/{blog_id}/neighbors`
- `GET /api/graph/snapshots/latest`
- `GET /api/graph/snapshots/{version}`
- `GET /api/stats`
- `GET /api/filter-stats`

源码位置： [backend/main.py](../backend/main.py)

补充说明：

- 浏览器实际访问的是 `frontend` 服务。
- [frontend/server.py](../frontend/server.py) 会把 `/api/*` 代理到 `backend`。
- 因此“公共 API 由 backend 提供”与“浏览器经 frontend 访问 API”这两件事同时成立。
- blog 规则重扫接口同样由 `frontend -> backend` 访问，但实际归并动作发生在 persistence 层。

### 2.2 Admin API

Admin API 同样由 `backend` 暴露，但统一位于 `/api/admin/*` 下，并要求 `Authorization: Bearer <token>`。该 token 可以是 legacy `HEYBLOG_ADMIN_TOKEN`，也可以是已登录、已验证邮箱且 `role=admin` 的用户 session token：

- `GET /api/admin/runtime/status`
- `GET /api/admin/runtime/current`
- `POST /api/admin/runtime/start`
- `POST /api/admin/runtime/stop`
- `POST /api/admin/runtime/run-batch`
- `POST /api/admin/crawl/bootstrap`
- `POST /api/admin/crawl/run`
- `POST /api/admin/blogs/requeue-failed`
- `POST /api/admin/database/reset`
- `GET /api/admin/blog-labeling/candidates`
- `GET /api/admin/blog-labeling/counts`
- `GET /api/admin/blog-labeling/tags`
- `POST /api/admin/blog-labeling/tags`
- `GET /api/admin/blog-labeling/parquet-status`
- `POST /api/admin/blog-labeling/parquet-sync`
- `POST /api/admin/blog-labeling/parquet-rebuild`
- `GET /api/admin/blog-labeling/parquet-export`
- `POST /api/admin/blog-labeling/title-preview`
- `PUT /api/admin/blog-labeling/labels/{blog_id}`
- `GET /api/admin/recommendation-stats`
- `GET /api/admin/hourly-stats`
- `GET /api/admin/users`
- `PATCH /api/admin/users/{user_id}/role`

补充脚本：

- `scripts/migrate_blog_label_assignment_ids.py`：兼容性迁移脚本，把历史 `blog_label_assignments.blog_id` 对齐到稳定的 URL subject id。默认 dry-run，`--apply` 才会写库。
  - 容器内运行前需要重新构建 `persistence-api` 镜像，因为脚本目录是随镜像一起复制进去的。
- `scripts/import_legacy_label_counts.py`：把早期 `url,title,label` CSV 直接导入当前 URL-keyed `blog_labels`。默认 dry-run；传 `--apply --clear-existing` 会先清空 `blog_labels`，再按 normalized URL 聚合写入 `label_id` 计数字典。传 `--titles-only --apply` 时只按 CSV 快速回填已存在 `blog_labels.title`，不创建新行，也不改变 `label_id` 计数。旧标签 `others` 会映射为当前 `other`。

认证语义：

- Admin API 接受 legacy `HEYBLOG_ADMIN_TOKEN`，也接受已登录、已验证邮箱且 `role=admin` 的用户 session token。
- 未提供 token：`401 admin_auth_required`
- token 不合法：`403 admin_auth_invalid`
- token 属于普通用户或未验证 admin 候选账号：`403 admin_auth_forbidden`
- 未配置 `HEYBLOG_ADMIN_TOKEN` 且未开启 `HEYBLOG_ADMIN_DEV_BYPASS=true`，同时请求也不是合法 admin 用户 session：`503 admin_auth_not_configured`

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
- `raw_discovered_urls`: `raw_discovered_urls` 表中的原始发现 URL 总数；crawler 会用它执行 `HEYBLOG_RAW_DISCOVERED_URL_LIMIT` 启动保护，配置为 `-1` 时不限制

#### `GET /api/filter-stats`

用途：返回基于配置化 URL 过滤链的统计结果，用于展示规则过滤漏斗、RSS/模型成功判定分流，以及最终入库博客数量。

返回结构：

- `by_filter_reason`: 兼容字段。按过滤链顺序排列的对象；每个 value 表示执行完该过滤器后仍然剩余多少 URL，末尾包含 `success` 与 `blogs`
- `rule_drops`: 每个 `rule:*` 规则实际拦截的 URL 数量
- `success_sources`: `success` URL 的判定来源计数
  - `rss`: 通过 RSS/Atom feed discovery 判定为博客
  - `model`: 通过模型共识判定为博客
  - `unknown`: 缺少来源字段的成功 URL，通常只会出现在旧数据或手工导入数据中
- `funnel`: 面向前端可视化的关键漏斗节点
  - `raw`: 进入过滤链的标准化 URL 总数
  - `after_rules`: 通过全部确定性规则后的候选 URL 数
  - `model_rejected`: 被模型共识拒绝的 URL 数
  - `success`: 成功判定为博客 URL 的总数
  - `blogs`: 实际入库博客总数

统计语义：

- 顺序由 `runtime_resources/filter_chain.toml` 中启用的过滤器顺序决定
- 统计基础来自持久化表 `raw_discovered_urls`
- `rule:duplicate_url` 是过滤链前置状态：同一个 `normalized_url` 已经存在更小 `id` 的 raw 行时，当前 raw URL 会提前标记为重复，不再进入后续过滤链；更大 `id` 的未来/后续行不会反向影响当前行
- URL 通过 RSS 或模型成功判定后仍写为 `status=success`，同时用 `accepted_by` 记录来源
- `success` 与 `blogs` 可能不同，因为 `upsert_blog` 会按 `identity_key` 合并同一站点

响应示例：

```json
{
  "by_filter_reason": {
    "raw": 1000,
    "rule:duplicate_url": 930,
    "rule:same_domain": 880,
    "rss:rss_feed_found": 700,
    "model:model_consensus_all_non_blog": 620,
    "success": 620,
    "blogs": 590
  },
  "rule_drops": {
    "rule:duplicate_url": 70,
    "rule:same_domain": 50
  },
  "success_sources": {
    "rss": 260,
    "model": 360,
    "unknown": 0
  },
  "funnel": {
    "raw": 1000,
    "after_rules": 700,
    "model_rejected": 80,
    "success": 620,
    "blogs": 590
  }
}
```

### 3.3 用户认证接口

#### `POST /api/auth/register`

用途：提交邮箱和密码并发送验证邮件。该接口只创建临时待验证注册记录，不创建登录 session，也不会把用户账号写入 `users`。只有用户通过验证码/验证链接完成 `/api/auth/email/verify/confirm` 后，系统才会创建持久化用户账号。游客无需入库；未登录请求即游客身份。

请求体：

```json
{
  "email": "user@example.com",
  "password": "long enough"
}
```

成功响应：

```json
{
  "sent": true,
  "verification_token": "dev-verification-token",
  "verification_url": "http://127.0.0.1:3000/profile?verify_token=dev-verification-token",
  "expires_at": "2026-06-12T00:00:00+00:00"
}
```

错误语义：

- `409 email_already_registered`
- `409 email_registration_pending`
- `422 invalid_email`
- `422 password_too_short`
- `502 email_delivery_failed`

#### `POST /api/auth/login`

用途：使用邮箱和密码登录，创建新的 bearer session。请求体同注册接口，成功响应也同注册接口。

错误语义：

- `401 invalid_credentials`
- `422 invalid_email`

#### `GET /api/auth/me`

用途：读取当前登录用户资料。

请求头：

- `Authorization: Bearer <session-token>`

错误语义：

- `401 auth_required`

#### `POST /api/auth/logout`

用途：注销当前 session token。请求头同 `/api/auth/me`。

#### `POST /api/auth/email/verify/request`

用途：为已经创建但尚未验证的普通用户或 admin 用户重新生成邮箱验证 token。未知邮箱和仍处于注册待验证阶段、尚未持久化的邮箱返回中性成功语义，避免暴露账号是否存在；待验证新注册应继续使用注册邮件中的链接完成账号创建。

邮件通道由 `persistence-api` 的 `HEYBLOG_EMAIL_PROVIDER` 控制。默认 `disabled` 模式不会连接 SMTP，并会在响应体中返回一次性验证 token/link，方便本地调试和手动验证。设置 `HEYBLOG_EMAIL_PROVIDER=smtp` 后，系统会把验证链接发送到用户邮箱；生产环境应设置 `HEYBLOG_EMAIL_DEV_EXPOSE_TOKENS=false`，让 API 响应只保留发送状态和过期时间，不暴露明文 token。

请求体：

```json
{
  "email": "user@example.com"
}
```

成功响应：

```json
{
  "sent": true,
  "verification_token": "dev-verification-token",
  "verification_url": "http://127.0.0.1:3000/profile?verify_token=dev-verification-token",
  "expires_at": "2026-06-10T00:00:00+00:00"
}
```

生产 SMTP 且关闭 dev token 暴露后的成功响应：

```json
{
  "sent": true,
  "expires_at": "2026-06-10T00:00:00+00:00"
}
```

错误语义：

- `502 email_delivery_failed`

#### `POST /api/auth/email/verify/confirm`

用途：消费邮箱验证邮件链接中的一次性 token。对于新注册 token，该接口先创建持久化用户账号，再返回已验证用户资料；对于历史未验证账号 token，该接口把已有用户标记为已验证。token 只保存 hash，过期或已消费后不可复用。浏览器打开 `/profile?verify_token=...` 时，前端会自动调用该接口完成验证，随后提示用户登录。

请求体：

```json
{
  "token": "dev-verification-token"
}
```

返回：创建或更新后的用户资料。新注册用户默认 `role=user`、`email_verified=true`，不会自动创建登录 session。

#### `POST /api/auth/password/forgot`

用途：请求密码重置 token。未知邮箱返回中性成功语义。

请求体：

```json
{
  "email": "user@example.com"
}
```

默认开发响应包含可直接使用的 `reset_token` 与 `reset_url`。设置 `HEYBLOG_EMAIL_PROVIDER=smtp` 后，系统会把 reset link 发送到用户邮箱；生产环境应设置 `HEYBLOG_EMAIL_DEV_EXPOSE_TOKENS=false`，让 API 响应隐藏明文 reset token。后端始终只持久化 token hash。

生产 SMTP 且关闭 dev token 暴露后的成功响应：

```json
{
  "sent": true,
  "expires_at": "2026-06-10T00:00:00+00:00"
}
```

错误语义：

- `502 email_delivery_failed`

#### `POST /api/auth/password/reset`

用途：消费一次性密码重置 token，设置新密码，并撤销该用户所有旧 session。

请求体：

```json
{
  "token": "dev-reset-token",
  "password": "new long enough"
}
```

返回：更新后的用户资料。

#### `GET /api/me/label-selections`

用途：返回当前登录用户最近的随机博客标注选择。

查询参数：

- `limit`: 可选，默认 `50`，最大 `100`

返回字段：

- `id`
- `normalized_url`
- `label_id`
- `label`
- `label_name`
- `created_at`
- `updated_at`
- `blog`: 若当前 URL 仍在 `blogs` 中，则返回博客摘要；否则为 `null`

#### `GET /api/me/label-stats`

用途：返回当前登录用户的随机博客标注汇总。

请求头：

- `Authorization: Bearer <session-token>`

返回字段：

- `label_count`: 当前用户总共保存的标注选择次数

### 3.4 Blog 与图结构查询

统一标识约定：

- 本节所有路由中的 `blog_id` 都表示业务主键 `blogs.blog_id`，不再表示数据库行主键 `blogs.id`
- blog 节点、详情、邻居摘要等响应会显式返回 `blog_id`

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
- `acceptance_status`: 博客接受状态筛选，默认 `ACCEPTED`；允许 `ACCEPTED`、`UNKNOWN`、`REJECTED`。该字段表示 URL 是否已被 seed、RSS 或模型确认为博客，独立于 `crawl_status`
- `sort`: 排序方式，允许 `id_asc`、`id_desc`、`recent_activity`、`connections`、`recently_discovered`、`random`
- `has_title`: 是否要求有标题；支持布尔值，也接受 `1/0`、`true/false`、`yes/no`
- `has_icon`: 是否要求有 icon；支持布尔值，也接受 `1/0`、`true/false`、`yes/no`
- `min_connections`: 最小连接度阈值，负数会被归一化为 `0`

归一化与排序规则：

- 空白字符串会被视为未传参
- 非法 `status` 返回 `422`
- 非法 `statuses` 返回 `422`
- 非法 `acceptance_status` 返回 `422`
- 非法 `sort` 返回 `422`
- 当 `statuses` 存在时优先于 `status`，用于同时查询多个 `crawl_status`
- 默认只返回 `acceptance_status=ACCEPTED` 的 URL；`crawl_status=FAILED` 只表示最近一次抓取尝试失败，不表示该 URL 不是博客
- `has_title` / `has_icon` 仅在传入真值时启用过滤；传入假值会保留参数值但不额外筛掉空字段记录
- `id_asc` 按业务 `blog_id ASC`
- `recent_activity` 按 `activity_at DESC, connection_count DESC, blog_id DESC`
- `connections` 按 `connection_count DESC, activity_at DESC, blog_id DESC`
- `recently_discovered` 按 `created_at DESC, blog_id DESC`
- `random` 按用户反馈权重随机返回，适合“随机博客”类入口；该模式会过滤掉 `blog_labels` 中已有非 `blog` 管理员标签计数的 URL
- `id_desc` 按业务 `blog_id DESC`
- 若请求页码超出最后一页且结果集非空，服务端会回退到最后一页，并在响应中返回实际生效页码

响应结构见“数据模型”章节中的 `BlogCatalogPageRecord`。

当前前端使用方式：

- 首页搜索框使用 `page=1&page_size=30&url=<输入 URL>&sort=id_desc` 查询已发现博客，并把返回项渲染为可滚动结果列表。

#### `POST /api/recommendations/random-blog-batches`

用途：随机博客页请求一组新的推荐卡片，并把本次刷新作为一条可追踪的 recommendation request 持久化。服务端会同时写入有序 impression 记录，所以后续点击、详情打开和标注事件可以归因到“哪次刷新中的第几个 URL”。

请求体：

```json
{
  "count": 9,
  "visitor_id": "visitor_lx7...",
  "session_id": "session_lx7...",
  "source": "random_page",
  "page_url": "http://localhost:3000/random",
  "context": {
    "refresh_kind": "manual"
  }
}
```

认证说明：

- 未登录也可调用；`visitor_id` 与 `session_id` 由前端本地生成，用于匿名统计。
- 登录后可带 `Authorization: Bearer <session-token>`；backend 会把用户 ID 转发给 persistence 以便后续用户维度分析。

行为说明：

- 当前 surface 固定为 `random_blog_page`
- 当前 strategy 固定为 `weighted_random`，`strategy_version = v1`
- 只返回 `crawl_status=FINISHED` 且 `acceptance_status=ACCEPTED` 的博客
- 随机排序复用 catalog 的 `sort=random` 权重逻辑：管理员非 blog 标签会过滤，用户公开反馈会影响权重
- `count` 当前允许 `1..50`；随机页默认请求 `9`

成功响应示例：

```json
{
  "request_uuid": "r_abc",
  "surface": "random_blog_page",
  "strategy": "weighted_random",
  "strategy_version": "v1",
  "visitor_id": "visitor_lx7",
  "session_id": "session_lx7",
  "requested_count": 9,
  "served_count": 9,
  "created_at": "2026-06-07T13:30:00+00:00",
  "items": [
    {
      "id": 12,
      "url": "https://blog.example.com/",
      "normalized_url": "https://blog.example.com/",
      "request_uuid": "r_abc",
      "impression_id": 101,
      "position": 1
    }
  ]
}
```

错误语义：

- `401`: bearer token 非法或过期
- `422`: count、visitor/session ID 或 JSON context 非法

#### `POST /api/recommendation-events`

用途：记录随机博客卡片上的用户行为。事件以 `event_uuid` 幂等写入，适合前端在详情跳转、外链打开、标注选择等动作发生时尽力而为上报。

请求体：

```json
{
  "event_uuid": "event_lx7...",
  "event_type": "detail_open",
  "blog_id": 12,
  "visitor_id": "visitor_lx7...",
  "session_id": "session_lx7...",
  "entrance_kind": "random_blog_page",
  "entrance_url": "http://localhost:3000/random",
  "request_uuid": "r_abc",
  "impression_id": 101,
  "position": 1,
  "interaction_order": 1,
  "client_event_at": "2026-06-07T13:31:00.000Z",
  "attributes": {
    "label": "blog"
  }
}
```

支持的 `event_type`：

- `click`
- `detail_open`
- `external_open`
- `label_select`
- `refresh`
- `dismiss`
- `copy_url`

行为说明：

- 同一个 `event_uuid` 重复上报时不会重复计数，响应中会返回 `duplicate: true`
- `entrance_kind` 与 `entrance_url` 为必填字段。`entrance_kind` 使用稳定、可聚合的路口种类，例如 `random_blog_page`、`home_search_result`、`blog_detail_discovery_path`、`blog_detail_relation_graph`；`entrance_url` 保留触发动作时的原始页面 URL 或上下文 URL，便于追溯具体来源。
- 若传入 `request_uuid` 或 `impression_id`，服务端会校验它们存在且与当前 blog 的 `normalized_url` 匹配
- 前端不应因为事件上报失败而阻塞用户跳转或标注主流程
- 持久化时事件落到 `blog_interactions`，以 `normalized_url` 作为博客归因键；其中 `entrance_kind` 与 `entrance_url` 单独存列并建立索引，便于按稳定路口维度统计详情打开、外链打开和标签选择。

错误语义：

- `404`: 目标 blog 不存在
- `401`: bearer token 非法或过期
- `422`: event type、request/impression 归因或 JSON attributes 非法

#### `GET /api/blogs/{blog_id}/stats`

用途：返回单个博客在推荐系统中的曝光和交互统计，供详情页或后续运营面板展示。

成功响应示例：

```json
{
  "blog_id": 12,
  "normalized_url": "https://blog.example.com/",
  "impressions": 20,
  "clicks": 1,
  "detail_opens": 3,
  "external_opens": 0,
  "label_selects": 2,
  "unique_visitors": 5,
  "ctr": 0.2,
  "last_interaction_at": "2026-06-07T13:31:00+00:00",
  "by_event_type": {
    "detail_open": 3,
    "label_select": 2
  }
}
```

错误语义：

- `404`: 目标 blog 不存在

#### `GET /api/admin/recommendation-stats`

用途：返回推荐请求、曝光和交互的策略级汇总。该接口位于 admin API 下，需要 `Authorization: Bearer <HEYBLOG_ADMIN_TOKEN>`。

成功响应示例：

```json
{
  "total_requests": 10,
  "total_impressions": 90,
  "total_interactions": 12,
  "by_strategy": [
    {
      "surface": "random_blog_page",
      "strategy": "weighted_random",
      "strategy_version": "v1",
      "requests": 10,
      "impressions": 90,
      "clicks": 8,
      "unique_visitors": 6,
      "ctr": 0.0888888889
    }
  ]
}
```

#### `GET /api/admin/hourly-stats`

用途：返回后台统计小时快照，并在读取时刷新当前自然小时的数据。该接口位于 admin API 下，需要 `Authorization: Bearer <HEYBLOG_ADMIN_TOKEN>` 或已验证 admin 用户 session token。

查询参数：

- `limit`: 返回最近多少个自然小时快照，默认 `24`，最大 `168`

统计语义：

- 数据写入 `admin_hourly_stats` 表，每条记录对应一个 UTC 自然小时窗口 `[hour_start, hour_start + 1h)`
- `user_count`: 当前 active 用户总数
- `random_request_count`: 该小时内 random blog 推荐请求数
- `random_impression_count`: 该小时内 random blog 推荐曝光数；随机页每次通常请求 9 个
- `detail_open_count`: 该小时内 random blog 卡片详情打开次数
- `external_open_count`: 该小时内 random blog 卡片外链打开次数
- `detail_ctr`: `detail_open_count / random_impression_count`
- `external_ctr`: `external_open_count / random_impression_count`
- `total_click_ctr`: `(detail_open_count + external_open_count) / random_impression_count`

成功响应示例：

```json
{
  "current_hour": {
    "id": 1,
    "hour_start": "2026-06-11T10:00:00+00:00",
    "user_count": 12,
    "random_request_count": 3,
    "random_impression_count": 27,
    "detail_open_count": 4,
    "external_open_count": 5,
    "detail_ctr": 0.1481481481,
    "external_ctr": 0.1851851852,
    "total_click_ctr": 0.3333333333,
    "refreshed_at": "2026-06-11T10:05:00+00:00",
    "created_at": "2026-06-11T10:05:00+00:00"
  },
  "latest": {
    "id": 1,
    "hour_start": "2026-06-11T10:00:00+00:00",
    "user_count": 12,
    "random_request_count": 3,
    "random_impression_count": 27,
    "detail_open_count": 4,
    "external_open_count": 5,
    "detail_ctr": 0.1481481481,
    "external_ctr": 0.1851851852,
    "total_click_ctr": 0.3333333333,
    "refreshed_at": "2026-06-11T10:05:00+00:00",
    "created_at": "2026-06-11T10:05:00+00:00"
  },
  "items": []
}
```

#### `POST /api/blogs/user-seeds`

用途：当首页 URL 搜索没有命中时，允许用户提交一个完整博客链接作为用户来源 seed。该接口只执行确定性规则过滤，跳过 RSS discovery 与模型共识；规则通过后会把 URL 同时写入 `blogs` 与 `seeds`。

请求体：

```json
{
  "homepage_url": "https://blog.example.com"
}
```

成功语义：

- URL 先按当前 identity/canonicalization 规则归一化
- 只运行过滤链中的 rule filters；不会因为缺少 RSS、模型未加载或模型判非博客而拒绝
- 规则通过后，`blogs.acceptance_status = ACCEPTED`
- `blogs.accepted_by = user`
- 新建或历史 `FAILED` 博客会处于 `crawl_status = WAITING`，因此可被 crawler 领取并抓取友链
- 已经 `FINISHED` 的博客不会被强制重置为 `WAITING`
- 同一 URL 会 upsert 到 `seeds` 表，当前用 `source_path = user` 标记用户来源

成功响应示例：

```json
{
  "status": "QUEUED",
  "blog_id": 123,
  "inserted": true,
  "blog": {
    "id": 123,
    "blog_id": 123,
    "url": "https://blog.example.com/",
    "normalized_url": "https://blog.example.com/",
    "domain": "blog.example.com",
    "acceptance_status": "ACCEPTED",
    "accepted_by": "user",
    "crawl_status": "WAITING"
  }
}
```

错误语义：

- URL 格式无法归一化或规则过滤拒绝时返回 `422`

#### `GET /api/icons/proxy`

用途：把已知 icon URL 作为同源图片返回，供 3D 图谱 WebGL texture 加载使用。

查询参数：

- `url`: 绝对 `http` / `https` 图片 URL。前端通常传入 `icon_url` 或 favicon API fallback URL。

响应：

- 成功时返回远端图片字节，`Content-Type` 沿用远端图片 MIME，并设置 `Cache-Control: public, max-age=86400`
- 仅允许公网 HTTP(S) URL；localhost、私网、link-local、reserved 等地址会返回 `422`
- 远端超时返回 `504`
- 远端非 2xx、非图片 MIME、或响应超过 1MB 时返回 `502`

说明：

- 该接口不改变 `blogs.icon_url` 的持久化语义，只解决浏览器 WebGL 对跨域 texture 的 CORS 要求
- 普通 `<img>` 展示仍可直接使用 `icon_url` 或前端 favicon fallback；图谱纹理建议统一使用该代理后的同源 URL

#### `POST /api/blogs/{blog_id}/user-labels`

用途：随机博客页为单个博客 URL 增加一次公共用户标注。该接口写入 `blog_labels_userlabel`，表结构和 `blog_labels` 一致，均按 `normalized_url` 存储 `title` 与 `label_id` 计数字典；不会修改训练用的 `blog_labels`。

请求体：

```json
{
  "label": "other",
  "previous_label": "blog"
}
```

认证说明：

- 未登录也可提交；服务端只更新公开聚合计数。
- 登录后提交时可带 `Authorization: Bearer <session-token>`；服务端会同时记录该用户对当前 URL 的最新选择，并用已有选择推导旧 label，因此跨刷新切换也不会重复累加同一用户的旧选择。

行为说明：

- `label` 只接受随机博客页使用的四类标签：`blog`、`company`、`other`、`unknown`
- `previous_label` 可选；用于随机博客页内的单 URL 单选择切换。若传入且与 `label` 不同，服务端会先把旧 label 计数减 `1`，再把新 label 计数加 `1`
- 前端同一张 URL 卡片重复点击已选中的 label 不会再次请求接口，也不会重复累加计数
- 随机博客加权时，所有 URL 默认权重为 `10`；设用户表中非 `blog` 计数为 `y`，权重为 `10 / (1 + y)`；`blog` 正反馈不再提升随机权重
- 权重只影响 `sort=random` 的随机排序；管理员训练标签只负责过滤非 blog，不会被用户标注改变

错误语义：

- `404`: 目标 blog id 不存在
- `409`: 目标不是已完成博客
- `422`: label 非法
- `401`: bearer token 非法或过期

成功响应示例：

```json
{
  "blog_id": 12,
  "label_id": {
    "1": 3,
    "3": 1
  },
  "labels": [
    {
      "id": 1,
      "name": "blog",
      "slug": "blog",
      "count": 3,
      "labeled_at": "2026-05-26T00:20:00+00:00"
    }
  ],
  "label_slugs": ["blog", "other"],
  "last_labeled_at": "2026-05-26T00:20:00+00:00",
  "is_labeled": true
}
```

- 统一 discovery 主入口固定以 `statuses=WAITING,PROCESSING&sort=id_asc` 渲染“当前博客状态”板块
- 发现页只请求当前页，不再拉全量 blog 列表
- 该请求默认不做 5 秒轮询，也不依赖窗口聚焦自动刷新
- 发现页会利用新增字段直接渲染博客卡片的活跃度、连接度与身份完整度提示

#### `GET /api/blogs/lookup?url=...`

用途：对单个博客首页 URL 做数据库存在性判断，供统一 discovery 页的“检查博客 URL 是否已收录”区域使用。

查询参数：

- `url`: 博客首页 URL，必填

匹配阶梯：

- 先复用 blog identity canonicalization 规则，把输入归一化为 `normalized_query_url`
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
- 返回 `discovery_path` 描述该博客进入网络的路径：手动 seed/user 添加，或由 crawler 沿友链逐级发现
- 返回 `relation_graphs` 描述详情页“博客关联”模块使用的两层入链/出链关系图；两层深度内的入链/出链关系完整返回，不按节点或边数量裁剪

额外字段：

- `crawl_status`: 当前抓取执行状态，例如 `WAITING`、`PROCESSING`、`FAILED`、`FINISHED`；详情页会直接展示该字段
- `crawl_error_kind`: 最近一次抓取失败分类；当 `crawl_status=FAILED` 时，详情页会把该字段作为失败原因展示，例如 `timeout`、`page_too_large`、`http_status`、`request_error`
- `incoming_edges`: 所有 `to_blog_id == blog_id` 的边，每条边额外携带 `neighbor_blog`
- `outgoing_edges`: 所有 `from_blog_id == blog_id` 的边，每条边额外携带 `neighbor_blog`
- `recommended_blogs`: “朋友的朋友”推荐列表，规则是“当前博客的友链认识、但当前博客还没直接认识的博客”
- `discovery_path`: 发现路径。`mode=manual` 表示该博客由 `accepted_by=seed/user` 手动进入网络；`mode=crawled` 表示通过 `raw_discovered_urls` 从当前博客逐级追溯 source blog，直到 seed/user 源头、无法继续追溯或检测到循环；正常长路径会完整返回，不按固定深度截断
- `relation_graphs`: `{ incoming, outgoing }`，两个图默认各包含从当前博客出发的 2 层关系；`incoming` 沿入链向上追溯，`outgoing` 沿出链向下展开；两层深度内不按节点或边数量裁剪

其中 `neighbor_blog` 是详情页使用的邻居摘要，字段为：

- `id`
- `blog_id`
- `domain`
- `title`
- `icon_url`

### 3.5 管理员博客人工标注台

#### `GET /api/admin/blog-labeling/candidates`

用途：返回博客人工标注台使用的候选列表。标注台展示队列请求 `labeled=false`，只显示模型过滤前已经处理过、适合人工标注的 raw URL：`raw_discovered_urls.status = success` 或 `raw_discovered_urls.status LIKE 'model:%'`，且该 URL 在 `blog_labels` 中不存在。候选 ID 始终使用当前 `raw_discovered_urls.id`，便于前端继续按候选行保存；若该 raw URL 已有对应 blog，则只借用 blog 上的 title/icon 等展示字段，不把 `blogs.blog_id` 作为标注 ID，也不会为了标注补建轻量 blog 行。已标注候选展示 title 时优先使用 `blog_labels.title`；若旧 label 行没有 title 但当前 `blogs` 有对应 title，候选加载会临时回填 `blog_labels.title` 并返回该 title。实际 label 会按 `blog_labels.normalized_url` 长期保存，避免清库重爬后 raw/blog id 改变导致标注丢失。

查询参数：

- `page`: 页码，默认 `1`
- `page_size`: 每页条数，默认 `50`，最终会被限制在 `1..200`
- `q`: 模糊搜索，匹配 `blogs.title` / `blog_labels.title` / `domain` / `url` / `normalized_url`
- `label`: 标签 `slug` 精确筛选，例如 `blog`、`official`、`government`
- `labeled`: 标注状态筛选；支持 `1/0`、`true/false`、`yes/no`。标注台候选队列固定传 `false`，统计查询可传 `true`
- `sort`: 排序方式，允许 `id_desc`、`recent_activity`、`recently_labeled`

响应结构：

- 复用 `BlogRecord` 的主体字段
- 追加 `label_id`、`labels`、`label_slugs`、`last_labeled_at`、`is_labeled`
- 顶层追加 `available_tags`，用于前端渲染可选标签与新建标签后的刷新
- 分页包装结构与 `GET /api/blogs/catalog` 一致

语义说明：

- 未标注状态通过 `labels = []` 与 `is_labeled = false` 表达，不把“未标注”落成特殊标签
- `label_id` 是 label id 到计数的 JSON object，例如 `{"1": 10, "2": 1}`
- 一个 URL 可以同时拥有多个标签计数；`label` 查询参数表达“包含该标签”的筛选语义，而不是单值相等比较
- 候选范围不再等同于 `crawl_status == FINISHED`；模型过滤掉的 `model:*` raw URL 也会进入标注台，避免训练数据只覆盖模型已放行样本
- 标注保存不要求目标一定存在于 `blogs`；保存时会先用候选 raw row id 解析出 `normalized_url`，再把 `normalized_url`、当前展示 `title`、`label_id` 写入单表 `blog_labels`
- 对只存在于 `raw_discovered_urls`、没有 `blogs.title` 的候选，前端加载页面时可调用 `POST /api/admin/blog-labeling/title-preview` 临时读取页面 `<title>`；该预览不写数据库，只有用户提交标注并在请求体传入 `title` 后才持久化到 `blog_labels.title`
- `rule:*`、平台/TLD/路径等非模型过滤结果不会进入该标注池
- 查询实现会按每个 `normalized_url` 的最早 labelable raw row 作为代表候选，并依赖 `raw_discovered_urls` 的 status / normalized URL 索引分页；打开 admin 页面或轮询刷新不应堆积全表 raw URL 聚合查询
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
      "label_id": {
        "1": 10,
        "5": 1
      },
      "labels": [
        {
          "id": 1,
          "name": "blog",
          "slug": "blog",
          "count": 10,
          "labeled_at": "2026-04-05T20:01:00+00:00"
        },
        {
          "id": 5,
          "name": "official",
          "slug": "official",
          "count": 1,
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
      "id": 1,
      "name": "blog",
      "slug": "blog",
      "created_at": null,
      "updated_at": null
    },
    {
      "id": 5,
      "name": "official",
      "slug": "official",
      "created_at": null,
      "updated_at": null
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

#### `GET /api/admin/blog-labeling/counts`

用途：返回标注台实时统计。该接口直接按 `blog_labels` 全表聚合，不依赖当前 raw URL 候选池；清空 crawler 数据或 raw id 变化不会影响已持久化 label 的统计。

响应结构：

```json
{
  "total_labeled": 2373,
  "by_label": {
    "blog": 651,
    "company": 226,
    "other": 1496,
    "unknown": 0
  }
}
```

语义说明：

- `total_labeled` 表示 `blog_labels.label_id` 非空的 URL 数
- `by_label` 表示包含该 label 的 URL 数；即使某个 URL 对同一 label 的计数大于 1，也只计为 1 个 URL
- label slug 来自 `blog_label_tags`，未知 id 会以数字字符串返回

#### `GET /api/admin/blog-labeling/tags`

用途：返回当前所有可用标签类型定义，供前端渲染和复用。标签定义保存在 `blog_label_tags`，用于解释 `blog_labels.label_id` 中的数字 key。

响应结构：

- 返回数组，每项包含 `id`、`name`、`slug`、`created_at`、`updated_at`
- 默认映射为：`blog=1`、`company=2`、`other=3`、`unknown=4`、`official=5`、`government=6`
- 标签按 id 升序返回

#### `POST /api/admin/blog-labeling/tags`

用途：创建或复用一个标签定义。该接口写入 `blog_label_tags`，使后续保存的 `label_id` 能稳定解析为 label 名称。

请求体：

```json
{
  "name": "government"
}
```

行为说明：

- 服务端会对 `name` 进行 trim，并生成稳定 slug
- 同一 slug 会返回相同的稳定 id；默认标签会使用固定 id
- 空白或非法名称返回 `422`

成功响应示例：

```json
{
  "id": 6,
  "name": "government",
  "slug": "government",
  "created_at": null,
  "updated_at": null
}
```

#### `GET /api/admin/blog-labeling/parquet-status`

用途：检查当前人工标注 parquet 快照状态，不修改文件。

响应结构：

```json
{
  "path": "/app/data/exports/blog-label-training.parquet",
  "filename": "blog-label-training.parquet",
  "exists": true,
  "saved_count": 200,
  "total_labeled": 237,
  "missing_count": 37,
  "batch_size": 100,
  "rewritten": false,
  "message": "已保存 200 条数据，总计有 label 的有 237 条数据。",
  "updated_at": "2026-05-24T18:50:18+00:00"
}
```

#### `POST /api/admin/blog-labeling/parquet-sync`

用途：检查保存的 parquet 文件是否已经包含所有有 label 的 URL 数据；若发现缺失、文件不存在、已保存数据多于当前数据库事实，或当前总量到达 100 条边界，则重写 parquet 快照。

行为说明：

- parquet 文件固定写入 `HEYBLOG_EXPORT_DIR/blog-label-training.parquet`
- 只保留三列：`url`、`title`、`label`；`title` 来自保存标注时写入的 `blog_labels.title`
- 语义与 CSV 导出一致，一个 `blog x label` 组合对应一行
- 补齐/重建以 `blog_labels` 为事实来源，导出所有已持久化 label；不要求 URL 仍存在于当前 raw URL 候选池
- 响应结构与 `parquet-status` 一致，`rewritten` 表示本次是否实际写入文件

#### `POST /api/admin/blog-labeling/parquet-rebuild`

用途：重置 parquet 文件，并按当前保存流程从数据库中所有有 label 的数据重新生成一遍。该接口用于未来新增字段或保存流程变化时避免在旧文件上原地迁移。

响应结构与 `parquet-status` 一致；成功时 `rewritten` 为 `true`。

#### `GET /api/admin/blog-labeling/parquet-export`

用途：下载当前人工标注 parquet 文件。

响应类型：

- `application/vnd.apache.parquet`

行为说明：

- 下载前会先执行一次 `parquet-sync` 语义，确保缺失数据被补齐
- 响应头包含 `content-disposition: attachment; filename="blog-label-training.parquet"`
- 响应头包含 `x-heyblog-label-saved-count` 与 `x-heyblog-label-total-count`，便于调用方核对下载时的保存数量

#### `POST /api/admin/blog-labeling/title-preview`

用途：为标注台 raw-only 候选实时读取页面标题。该接口只返回临时展示 title，不写入 `blogs` 或 `blog_labels`。

请求体：

```json
{
  "url": "https://raw-only.example/"
}
```

成功响应：

```json
{
  "url": "https://raw-only.example/",
  "title": "Raw Only Blog"
}
```

行为说明：

- 仅接受 `http://` / `https://` URL
- 使用短超时抓取目标 HTML 并提取 `<title>`；失败时前端应继续允许按 URL/domain 标注
- 返回的 `title` 只有随 `PUT /api/admin/blog-labeling/labels/{blog_id}` 的 `title` 字段提交后，才会写入 `blog_labels.title`

#### `PUT /api/admin/blog-labeling/labels/{blog_id}`

用途：替换单个标注候选 URL 的整组人工标签。路径中的 `blog_id` 为兼容旧前端字段名，实际应传当前候选的 raw URL id。

请求体：

```json
{
  "title": "Raw Only Blog",
  "label_id": {
    "1": 10,
    "2": 1
  }
}
```

行为说明：

- 请求体中的 `label_id` 是完整替换语义，而不是增量 patch；key 为 label id 字符串，value 为该 label 的累计标注次数
- 兼容旧请求体 `{"tag_ids": [1, 5]}`，服务端会转换为 `{"1": 1, "5": 1}`
- 请求体中的 `title` 可选；传入非空值时优先作为 `blog_labels.title` 保存，适用于 raw-only 候选的临时 title
- 同一个 URL 可以同时拥有多个标签计数
- 传 `{}` 或空 `tag_ids` 表示“清空该 URL 当前所有标签”
- label 以 `blog_labels.normalized_url` 为长期键保存，并同步保存标注时的 `title`；清空 crawler 数据再重新爬取后，只要 URL 再次进入 labelable raw URL 池，就可用于导出原有标签

错误语义：

- `404`: 候选 raw URL id 不存在
- `409`: 目标不是 labelable raw URL，拒绝写入训练样本标签
- `422`: `label_id` / `tag_ids` 非法

成功响应示例：

```json
{
  "blog_id": 12,
  "label_id": {
    "1": 10,
    "2": 1
  },
  "labels": [
    {
      "id": 1,
      "name": "blog",
      "slug": "blog",
      "count": 10,
      "labeled_at": "2026-04-05T20:12:00+00:00"
    },
    {
      "id": 2,
      "name": "company",
      "slug": "company",
      "count": 1,
      "labeled_at": "2026-04-05T20:12:00+00:00"
    }
  ],
  "label_slugs": ["blog", "company"],
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
- 详情页不再额外请求 legacy 全量 blog / edge 接口
- incoming/outgoing 关系、邻居名称映射和“朋友的朋友”推荐都由后端在该接口内聚合

#### `GET /api/graph/views/core`

用途：返回图页默认使用的结构化初始子图。

常用查询参数：

- `strategy`: `degree` 或 `seed`
- `limit`: 默认子图规模上限，当前最大允许 `10000`
- `sample_mode`: `off` / `count` / `percent`；图谱页默认不启用采样
- `sample_value`: 当采样开启时的数量或百分比；`count` 会先用固定随机种子选择一个起点，再按 BFS 扩展到目标节点数，避免返回大量互不相连的随机点
- `sample_seed`: 固定随机种子，便于复现随机起点与补充分量顺序

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
- 当前图谱页用 0 到当前 blog 总数的滑块选择 `N`，默认值为 `min(200, total_blogs)`；点击确认后请求 `strategy=seed&limit=N`，直接按 blog id 升序选择前 N 个 blog 节点，并只返回这些节点之间的边。图谱节点不按 `crawl_status` 过滤，因为发现关系本身可能来自抓取失败或尚未完成的父节点；只要边的两端 blog 仍存在，就会参与图谱投影
- 当 `sample_mode != off` 时，会返回可复现的随机起点 BFS 子图；若起点所在连通分量不足目标规模，会按同一随机序列继续从其他分量 BFS 补足
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

### 3.4 搜索与日志现状

- 当前 public API 已不再暴露 legacy 的 `/api/logs` 与 `/api/search`。
- 运行日志统一由 `shared.observability` 输出到类型目录，默认是 `logs/app/`、`logs/error/`、`logs/access/`；每个类型目录下再按服务分目录，保存 `<service>-YYYYMMDD-HH.log` 小时切片，Docker Compose 中对应 `volumes/logs`。
- legacy `/internal/logs` 仍保留兼容入口，但当前不会把 crawl log 写入业务数据库。
- `search` 服务仍保留为内部可重建索引组件，供 health 检查与 reindex 维护链路使用，并在缓存为空时回退到 `persistence-api /internal/search-snapshot`。
- 浏览器当前没有直接依赖的 public 搜索页；public 发现主路径已经收敛到 `catalog / lookup / detail / graph views`。

### 3.5 管理员爬取执行接口

#### `POST /api/admin/crawl/bootstrap`

用途：导入种子博客。若 `seeds` 表已有记录，则直接以 `seeds` 表为来源回灌 `blogs`；仅当 `seeds` 表为空时才从 `seed.csv` 初始化。

调用链：

- `backend` -> `crawler /internal/crawl/bootstrap`

持久化行为：

- 每个 seed URL 会 upsert 到 `blogs`，并标记 `accepted_by=seed`
- 当 `seeds` 表为空时，会从 `seed.csv` 读取非空 URL，并同步 upsert 到 `seeds` 表，记录原始 URL、规范化 URL、domain、关联 `blog_id`、来源 CSV 路径与 CSV 数据行号
- 当 `seeds` 表不为空时，导入动作直接 replay `seeds` 表记录到 `blogs`，不会读取 `seed.csv`
- `seeds.normalized_url` 唯一；重复导入同一个 seed 会刷新记录，不会创建重复 seed 行
- 管理员数据库 reset 会保留 `seeds` 表数据，只清空其旧 `blog_id` 关联；下一次导入会重新把 seed 行关联到新建或复用的 blog

响应字段：

- `seed_path`: 配置的种子 CSV 文件路径；当 `seeds` 表不为空时，该字段仅表示 fallback CSV 路径
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

#### `POST /api/admin/database/reset`

用途：重置数据库中的 crawler 相关数据，便于测试和开发时快速回到初始状态。

行为说明：

- 仅允许在 crawler 运行器不处于 `starting/running/stopping` 时调用
- 若运行器忙碌，返回 `409`，错误详情为 `crawler_busy`
- 会清空 `blogs`、`edges`、`raw_discovered_urls`
- 不会删除 users、sessions、seeds、人工 label、recommendation 事件等其它表；`seeds.blog_id` 会置空以解除到 `blogs` 的引用
- backend 在数据库重置后会尝试调用 `search /internal/search/reindex`
- 即使 search 重建失败，数据库重置结果仍会返回，并附带 `search_reindexed=false`

成功响应示例：

```json
{
  "ok": true,
  "blogs_deleted": 12,
  "edges_deleted": 34,
  "raw_discovered_urls_deleted": 56,
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

#### `POST /api/admin/runtime/stop`

用途：请求后台 crawler 在安全点停止。

行为说明：

- 若当前已是 `idle`，直接返回当前快照
- 否则将状态切到 `stopping`

#### `POST /api/admin/runtime/run-batch`

用途：在运行器空闲时同步执行一批 crawl 任务。

补充说明：


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

用途：导入种子数据。该流程优先 replay `seeds` 表到 `blogs`；只有 `seeds` 表为空时才读取 seed CSV 并同步维护 `blogs` 与 `seeds`。

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

### `GET /internal/blogs/catalog`

用途：为 backend 提供分页 blog catalog 查询。

查询参数与返回 envelope 与 `GET /api/blogs/catalog` 一致。

补充说明：

- 归一化逻辑在 persistence 层统一处理，SQLite 与 PostgreSQL 共享同一套分页/筛选规则
- 支持 `sort`、`has_title`、`has_icon`、`min_connections` 等发现型参数
- 支持 `statuses` 多状态过滤与 `id_asc` 排序，供统一 discovery 队列视图使用
- blog 行数据会直接带上连接度、活跃度和身份完整度等派生字段

### `POST /internal/recommendations/random-blog-batches`

用途：为 backend 创建随机博客推荐批次，并写入 `recommendation_requests` 与 `recommendation_impressions`；曝光表以 `normalized_url` 持久归因，不保存 `blog_id`。

请求体字段与 `POST /api/recommendations/random-blog-batches` 一致，额外允许 backend 传入已解析的 `user_id`。

### `POST /internal/recommendation-events`

用途：为 backend 写入幂等推荐交互事件，数据落到 `blog_interactions`，并以 `normalized_url` 持久归因。

请求体字段与 `POST /api/recommendation-events` 一致，额外允许 backend 传入已解析的 `user_id`。其中 `entrance_kind` 与 `entrance_url` 仍为必填字段，persistence-api 会清洗长度并写入 `blog_interactions.entrance_kind` / `blog_interactions.entrance_url`。

### `GET /internal/blogs/{blog_id}/recommendation-stats`

用途：返回单个博客的推荐曝光、点击/详情打开、标注选择、独立访客和 CTR 统计。

返回结构与 `GET /api/blogs/{blog_id}/stats` 一致。

### `GET /internal/recommendation-stats`

用途：返回 strategy/surface/version 维度的推荐请求、曝光、交互和 CTR 汇总。

返回结构与 `GET /api/admin/recommendation-stats` 一致。

### `GET /internal/blogs/lookup?url=...`

用途：为 backend 提供数据库权威的博客 URL 存在性查询。

补充说明：

- 返回薄 lookup payload，而不是 catalog 分页 envelope
- 命中顺序固定为 `identity_key -> normalized_url -> empty`
- `match_reason` 只允许 `identity_key`、`normalized_url` 或 `null`

### `GET /internal/blogs/by-normalized-url?normalized_url=...`

用途：为 crawler 在遇到重复 raw URL 时解析已存在的目标 blog id。

响应：

```json
{
  "id": 1
}
```

补充说明：

- 未找到已接受 blog 时返回 `{ "id": null }`
- 该接口不改变 raw URL 去重语义；crawler 仍可把重复 URL 标记为 `rule:duplicate_url`，但会用这里返回的 id 补写新的源博客到目标博客的边
- 主要用于保留 A->C 已存在后，B 后续发现 C 时的 B->C 关系

### `GET /internal/queue/next`

用途：取出下一个待处理 blog，并立即将其状态更新为 `PROCESSING`。

行为说明：

- 只从 `crawl_status = 'WAITING'` 中选择
- 选中后立刻更新为 `PROCESSING`

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

### `POST /internal/blogs/requeue-failed`

用途：供 backend admin API 调用，把所有失败 blog 重新入队。

响应：

```json
{
  "requeued": 733
}
```

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

### `POST /internal/logs`

用途：legacy 兼容入口。当前实现会接收该请求并返回成功，但不会再把 crawl log
写入业务数据库；运行日志请查看统一日志目录。

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

- 清空 `blogs`、`edges`、`raw_discovered_urls`
- 不删除其它表；`seeds.blog_id` 会置空以解除到 `blogs` 的引用
- `logs_deleted` 固定返回 `0`

响应：

```json
{
  "ok": true,
  "blogs_deleted": 12,
  "edges_deleted": 34,
  "raw_discovered_urls_deleted": 56,
  "logs_deleted": 0
}
```

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
| `icon_url` | `string \| null` | 站点标签页 icon URL；仅在 crawler 从页面 metadata 提取并验证可访问后持久化，缺失或验证失败时为 `null`。前端可使用第三方 favicon API 做展示兜底，但不回写该字段 |
| `status_code` | `number \| null` | 最近抓取 HTTP 状态码 |
| `acceptance_status` | `string` | 博客接受状态，当前主要使用 `ACCEPTED` 与 `UNKNOWN`；该字段决定“是否被确认为博客” |
| `accepted_by` | `string \| null` | 接受来源，例如 `seed`、`rss`、`model` |
| `accepted_at` | `string \| null` | URL 被确认为博客的时间 |
| `crawl_error_kind` | `string \| null` | 最近一次抓取失败分类，例如 `timeout`、`page_too_large`、`http_status` |
| `crawl_error_message` | `string \| null` | 最近一次抓取失败详情摘要 |
| `last_crawl_attempt_at` | `string \| null` | 最近一次抓取尝试时间 |
| `successful_crawl_at` | `string \| null` | 最近一次成功完成抓取时间 |
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

### 5.3 BlogDetailPayload

字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `...BlogRecord` | `BlogRecord` | 详情页主博客信息 |
| `incoming_edges` | `BlogRelationRecord[]` | 指向当前博客的关系列表 |
| `outgoing_edges` | `BlogRelationRecord[]` | 当前博客指向外部的关系列表 |
| `recommended_blogs` | `BlogRecommendationRecord[]` | “朋友的朋友”推荐列表 |
| `discovery_path` | `BlogDiscoveryPath` | 发现路径摘要，从源头博客到当前博客的有序步骤 |
| `relation_graphs` | `{ incoming, outgoing }` | 两层入链/出链关系图，供详情页“博客关联”模块展示；两层深度内不按节点或边数量裁剪 |

其中：

- `BlogRelationRecord = EdgeRecord + { neighbor_blog: BlogNeighborSummary \| null }`
- `BlogRecommendationRecord = { blog, reason, mutual_connection_count, via_blogs }`
- `BlogNeighborSummary` 字段为 `id`、`domain`、`title`、`icon_url`
- `BlogDiscoveryPath = { mode, origin_source, origin_label, target_source, truncated, steps }`，其中 `truncated` 为历史兼容字段，当前始终为 `false`
- `BlogDiscoveryStep` 包含 `blog` 邻居摘要、`blog_id`、`url`、`domain`、`accepted_by`、`accepted_label`、`raw_id`、`raw_source_blog_id`、`raw_accepted_by`、`discovered_at`
- `BlogRelationGraph = { direction, focus_blog_id, depth, nodes, edges }`，其中 `direction` 为 `incoming` 或 `outgoing`，`depth` 默认是 `2`

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
- `backend` -> `persistence-api` 获取 blog catalog、blog detail、graph views、graph snapshots 与 stats
- `backend` -> `crawler` 获取运行时状态

### 6.2 写接口调用链

#### 种子导入

- 管理员前端/调用方 -> `POST /api/admin/crawl/bootstrap`
- `backend` -> `crawler /internal/crawl/bootstrap`
- `crawler` -> `persistence-api /internal/seeds` 检查是否已有持久化 seed
- 若已有 seed：`crawler` replay `seeds` 表到 `blogs`
- 若没有 seed：`crawler` 读取 `seed.csv`，再通过 `persistence-api /internal/blogs/upsert` 同时写入/刷新 `blogs` 与 `seeds`
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
- legacy 的 raw blog/edge/graph/log/search 公共读取端点已经移除，当前对外建议继续围绕 catalog、detail、graph view、user seed 和 admin runtime 组织能力
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
