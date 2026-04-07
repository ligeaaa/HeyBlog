# HeyBlog 配置参考

## 适合谁看

- 想知道某个环境变量该配给哪个服务的开发者
- 想确认默认值、Docker 覆盖值和本地运行差异的读者

## 建议前置阅读

- [README](../readme.md)
- [service-architecture.md](./service-architecture.md)

## 不包含什么

- 不展开业务含义与调用链背景，那部分见 [services-overview.md](./services-overview.md) 和 [service-architecture.md](./service-architecture.md)
- 不列出所有 FastAPI 参数或 Uvicorn CLI 参数，只覆盖仓库内显式使用的配置

## 最后核对源码入口

- [shared/config.py](../shared/config.py)
- [docker-compose.yml](../docker-compose.yml)

## 1. 统一配置入口

仓库内的应用级配置由 [shared/config.py](../shared/config.py) 中的 `Settings.from_env()`
统一加载。它会优先读取仓库根目录下的 `.env`，再回退到进程环境变量和代码默认值。

建议把本地可调配置维护在 `.env`，把团队基线维护在 `.env.example`。
Docker Compose 也会从仓库根目录的 `.env` 读取变量。

## 2. 应用级环境变量

| 变量 | 默认值 | 主要消费服务 | 说明 |
| --- | --- | --- | --- |
| `HEYBLOG_DB_PATH` | `./data/heyblog.sqlite` | `persistence-api` | SQLite 模式下的数据库文件 |
| `HEYBLOG_DB_DSN` | 未设置 | `persistence-api` | 设置后切换到 PostgreSQL |
| `HEYBLOG_SEED_PATH` | `./seed.csv` | `crawler` | 种子文件路径 |
| `HEYBLOG_EXPORT_DIR` | `./data/exports` | `crawler`、`persistence-api` | 导出图文件目录，也是 graph snapshot 的落盘目录 |
| `HEYBLOG_SEARCH_CACHE_DIR` | `./data/search-cache` | `search` | 搜索缓存目录，默认会写 `search-index.json` |
| `HEYBLOG_BACKEND_BASE_URL` | `http://127.0.0.1:8000` | `frontend` | 浏览器代理层转发到公共 API 的目标地址 |
| `HEYBLOG_CRAWLER_BASE_URL` | `http://127.0.0.1:8010` | `backend` | `backend` 调用 `crawler` 的内部地址 |
| `HEYBLOG_SEARCH_BASE_URL` | `http://127.0.0.1:8020` | `backend` | `backend` 调用 `search` 的内部地址 |
| `HEYBLOG_PERSISTENCE_BASE_URL` | `http://127.0.0.1:8030` | `backend`、`crawler`、`search` | 三个服务访问持久化边界的内部地址 |
| `HEYBLOG_USER_AGENT` | `HeyBlogBot/0.1 (+https://example.invalid/heyblog)` | `crawler` | 抓取请求使用的 User-Agent |
| `HEYBLOG_REQUEST_TIMEOUT_SECONDS` | `10.0` | `backend`、`crawler`、`search` | 内部 HTTP client 默认超时 |
| `HEYBLOG_MAX_NODES_PER_RUN` | `10` | `crawler` | 单次 crawl 默认节点上限 |
| `HEYBLOG_MAX_PATH_PROBES_PER_BLOG` | `50` | `crawler` | 单站点路径探测上限 |
| `HEYBLOG_CANDIDATE_PAGE_FETCH_CONCURRENCY` | `4` | `crawler` | 友链候选页抓取并发度，最小为 `1` |
| `HEYBLOG_RUNTIME_WORKER_COUNT` | `3` | `crawler` | runtime 持续抓取的 worker 数 |
| `HEYBLOG_MAX_FETCHED_PAGE_BYTES` | `2000000` | `crawler` | 单个页面允许读取的最大字节数；超限后当前 blog 直接记为 `FAILED`，超大页不会继续进入解析阶段 |
| `HEYBLOG_FRIEND_LINK_DOMAIN_BLOCKLIST` | 空 | `crawler` | 逗号分隔的域名黑名单 |
| `HEYBLOG_FRIEND_LINK_TLD_BLOCKLIST` | 空 | `crawler` | 逗号分隔的顶级域黑名单 |
| `HEYBLOG_FRIEND_LINK_EXACT_URL_BLOCKLIST` | 空 | `crawler` | 逗号分隔的精确 URL 黑名单 |
| `HEYBLOG_FRIEND_LINK_PREFIX_BLOCKLIST` | 空 | `crawler` | 逗号分隔的 URL 前缀黑名单 |

## 3. Docker Compose 里的默认覆盖

[docker-compose.yml](../docker-compose.yml) 为拆分运行时额外提供了这些默认值：

| 服务 | Compose 中设置的变量 | 作用 |
| --- | --- | --- |
| `frontend` | `HEYBLOG_DOCKER_BACKEND_BASE_URL` | 浏览器代理到 `backend` |
| `backend` | `HEYBLOG_DOCKER_PERSISTENCE_BASE_URL` | 读取持久化边界 |
| `backend` | `HEYBLOG_DOCKER_CRAWLER_BASE_URL` | 控制 `crawler` |
| `backend` | `HEYBLOG_DOCKER_SEARCH_BASE_URL` | 调用 `search` |
| `crawler` | `HEYBLOG_DOCKER_PERSISTENCE_BASE_URL` | 写入持久化边界 |
| `crawler` | `HEYBLOG_DOCKER_SEED_PATH` | 使用挂载后的种子文件 |
| `crawler` | `HEYBLOG_DOCKER_EXPORT_DIR` | 导出目录映射到 `volumes/exports` |
| `search` | `HEYBLOG_DOCKER_PERSISTENCE_BASE_URL` | 获取搜索快照 |
| `search` | `HEYBLOG_DOCKER_SEARCH_CACHE_DIR` | 搜索缓存映射到 `volumes/search-cache` |
| `persistence-api` | `HEYBLOG_DB_DSN` | 启用 PostgreSQL 后端 |

## 4. Postgres 容器级变量

这些变量不是 `shared/config.py` 的一部分，但在 Docker 运行时影响
`persistence-db` 容器：

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `POSTGRES_DB` | `heyblog` | 默认数据库名 |
| `POSTGRES_USER` | `heyblog` | 默认数据库用户名 |
| `POSTGRES_PASSWORD` | `heyblog` | 默认数据库密码 |

## 5. 本地手动启动时最容易踩的坑

1. `.env` 中建议保留宿主机地址，Docker Compose 内部地址单独放到 `HEYBLOG_DOCKER_*` 变量里。
2. `crawler` 和 `search` 即使本地跑，也会通过 HTTP 调 `persistence-api`，不是直接 import 仓储。
3. `frontend` 不是直接访问 `crawler` 或 `persistence-api`，它只认 `HEYBLOG_BACKEND_BASE_URL`。
4. 只改 `HEYBLOG_DB_PATH` 不会启用 PostgreSQL；真正切换数据库后端要设置 `HEYBLOG_DB_DSN`。

## 6. 相关文档

- [services-overview.md](./services-overview.md)
- [service-architecture.md](./service-architecture.md)
- [developer-workflows.md](./developer-workflows.md)
