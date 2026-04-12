# Crawler

`crawler/` 是 HeyBlog 爬虫服务和抓取核心逻辑的实现目录。

这部分代码主要解决三类问题：

1. 如何把“待抓取博客”从持久化层取出来，并驱动一次抓取或后台持续抓取。
2. 如何从一个博客首页出发，推断友链页、抽取候选链接、过滤出真正的博客主页。
3. 如何把抓取结果、运行态和导出文件暴露给其他服务或开发调试脚本使用。

如果你第一次读这个目录，建议先看：

1. `crawler/main.py`
2. `crawler/crawling/pipeline.py`
3. `crawler/crawling/orchestrator.py`
4. `crawler/crawling/discovery.py`
5. `crawler/crawling/extraction.py`
6. `crawler/filters.py`
7. `crawler/runtime/service.py`

## 目录结构

下面是去掉 `__pycache__` 后、带职责说明的目录视图：

```text
crawler/
├── README.md                         # crawler 包说明文档
├── __init__.py                       # 包标记文件，当前基本不承载业务逻辑
├── main.py                           # crawler 服务 HTTP 入口，组装 pipeline 和 runtime
├── filters.py                        # 友链候选 URL 的硬规则过滤器
├── export_service.py                 # 将当前图数据导出为 CSV / JSON / snapshot
├── utils.py                          # 文本清洗、去重等低层通用工具
├── contracts/                        # 对外或跨模块传递的结果 / 运行态结构
│   ├── __init__.py                   # contracts 子包导出入口
│   ├── results.py                    # 单次 crawl 结果结构，如 BlogCrawlResult
│   └── runtime.py                    # runtime worker / snapshot / aggregate 结构
├── crawling/                         # crawler 的真实抓取实现主目录
│   ├── __init__.py                   # crawling 子包标记文件
│   ├── bootstrap.py                  # 从 seed.csv 导入初始博客种子
│   ├── discovery.py                  # 从博客首页发现候选友链页
│   ├── extraction.py                 # 从候选页中抽取候选链接
│   ├── metadata.py                   # 提取站点标题、icon 等元信息
│   ├── normalization.py              # URL 清洗与博客身份归一规则
│   ├── orchestrator.py               # 单博客抓取主流程协调器
│   ├── pipeline.py                   # 单次 batch 级别的同步抓取入口
│   ├── decisions/                    # 链接决策链，负责把过滤规则组织成可扩展步骤
│   │   ├── __init__.py               # decisions 子包标记文件
│   │   ├── base.py                   # 决策步骤协议 UrlDecisionStep
│   │   ├── chain.py                  # 决策链 UrlDecisionChain
│   │   └── rules.py                  # 基于现有 filters 的规则决策器
│   └── fetching/                     # 网络抓取抽象与 HTTPX 实现
│       ├── __init__.py               # fetching 子包标记文件
│       ├── base.py                   # FetchResult / FetchAttempt / 协议 / 异常
│       └── httpx_fetcher.py          # 实际的 HTTPX 抓取实现，支持单抓与并发批抓
├── domain/                           # crawler 运行过程中的小型领域对象
│   ├── __init__.py                   # domain 子包标记文件
│   ├── blog_node.py                  # 当前待抓博客的 typed view
│   ├── crawl_state.py                # 回写 persistence 的抓取状态结构
│   ├── decision_outcome.py           # 决策链的标准输出结构
│   ├── exceptions.py                 # crawler 领域异常定义
│   └── friend_link_edge.py           # 发现到的博客连边结构
├── observability/                    # 日志与观测边界
│   ├── __init__.py                   # observability 子包标记文件
│   └── logger.py                     # crawler 日志封装，集中记录成功/失败事件
└── runtime/
    ├── __init__.py                   # runtime 子包导出入口
    ├── executor.py                   # 后台 runtime 线程执行器
    └── service.py                    # 常驻 runtime worker-pool 与状态管理
```

如果你只想抓重点，可以把这个目录理解成四层：

1. `main.py`：服务入口层
2. `crawling/`：真实抓取流程层
3. `runtime/`：后台持续运行层
4. `contracts/`、`domain/`、`observability/`：支撑结构层

## 按模块理解

### 1. 服务入口层

#### `main.py`

`crawler.main` 是 crawler 服务的 HTTP 入口。

它负责：

- 通过 `Settings.from_env()` 读取运行配置。
- 构建 `PersistenceHttpClient`，说明 crawler 服务默认不直接连数据库，而是通过 persistence-api 通信。
- 构建 `CrawlPipeline` 和 `CrawlerRuntimeService`。
- 暴露内部接口：
  - `GET /internal/health`
  - `POST /internal/crawl/bootstrap`
  - `POST /internal/crawl/run`
  - `GET /internal/runtime/status`
  - `GET /internal/runtime/current`
  - `POST /internal/runtime/start`
  - `POST /internal/runtime/stop`
  - `POST /internal/runtime/run-batch`

如果你想理解“服务是怎么启动起来的”，先从这里开始。

### 2. 单次抓取协调层

#### `crawling/pipeline.py`

这是“一次 crawl batch”的总调度器。

它负责：

- 导入 seed：`bootstrap_seeds()`
- 一次性跑若干个博客：`run_once()`
- 为每个博客调用 `process_blog_row()`
- 按优先队列和普通队列做公平 claim
- 在 batch 结束后调用 `ExportService.write_exports()`

可以把它理解成“同步抓取入口”。

典型调用路径：

1. 从 repository claim 一个待抓取 blog
2. 调用 `process_blog_row()`
3. 进入 `_crawl_blog()`
4. 把工作交给 `CrawlOrchestrator`
5. 更新失败状态或成功结果
6. 最后统一写导出文件

#### `crawling/bootstrap.py`

这个模块只做一件事：把 `seed.csv` 中的 URL 导入 `blogs` 表。

它会：

- 读取 CSV
- 用 `normalize_url()` 标准化 URL
- 调用 repository 的 `upsert_blog()`

所以 seed bootstrap 和真正抓取是两个阶段，不要混在一起理解。

### 3. 单博客抓取核心

#### `crawling/orchestrator.py`

这是整个 crawler 的核心流程文件。

它负责“抓一个博客”时的完整链路：

1. 抓首页
2. 提取站点元信息（标题、图标）
3. 从首页发现候选友链页
4. 并发抓候选友链页
5. 从候选页抽链接
6. 过滤出真正的博客主页
7. 持久化 blog 和 edge
8. 回写该博客的最终 crawl 结果

如果你想 debug “为什么某个博客没有抓到友链”，这里通常是最关键的入口。

### 4. 页面发现与内容抽取

#### `crawling/discovery.py`

这个模块解决的问题是：

“从首页 HTML 里，猜哪些页面可能是友链页？”

主要策略：

- 看 anchor 文本是否包含 `友链`、`blogroll`、`friends` 等关键词
- 看周围上下文文本
- 看 path 是否像 `/links`、`/friends` 这种常见模式
- 如果首页没发现明确入口，就构造一组 fallback path 去试

注意：

- discovery 只负责“找候选页面”
- 它不会在这里判断友链页里的每个链接是不是博客

#### `crawling/extraction.py`

这个模块解决的问题是：

“进入候选友链页后，应该从哪里抽链接？”

主要策略：

- 先找可能像友链区块的容器
- 根据 heading、容器文本、id/class、外链数量判断是否像友链区
- 如果多个容器重叠，优先更深、更具体的容器
- 如果没有明显命中，就选一个最合理的 fallback 容器

最终输出是 `ExtractedLink` 列表，包含：

- 绝对 URL
- anchor 文本
- 局部上下文文本

### 5. URL 标准化与身份归一

#### `crawling/normalization.py`

这里分成两层：

- `normalize_url()`：做轻量 URL 清洗
- `resolve_blog_identity()`：做更强的“站点身份归一”

`normalize_url()` 主要做：

- 小写 host
- 去 tracking 参数
- 统一 path 形式

`resolve_blog_identity()` 更进一步，会尝试：

- 折叠默认首页路径，如 `/index.html`
- 折叠安全的 host alias，如 `www`
- 在特定规则下折叠租户型子域名

当前 crawl 主流程更直接依赖 `normalize_url()` 做去重和落库，但 identity 规则为后续更强的站点归并提供了基础。

### 6. 链接过滤与决策链

#### `filters.py`

这个文件定义了硬规则过滤器，用来判断一个链接是否像“博客主页”。

当前策略偏保守，主要拦掉：

- 同域链接
- 非 HTTP(S)
- 已知平台域名，如社交平台、视频平台等
- 被配置 blocklist 命中的域名 / URL / 前缀
- 明显不是主页的 path，如 `/feed`、`/archive`
- 带 query / fragment 的非纯主页 URL
- 静态资源文件

当前版本已经移除了软评分逻辑，链接接受依赖硬规则通过与否。

#### `crawling/decisions/base.py`

定义决策接口 `UrlDecisionStep`。

它的价值在于把“链接决策”抽象成可插拔步骤，让未来可以加入更多规则或模型决策器。

#### `crawling/decisions/rules.py`

把 `filters.py` 的硬规则包装成一个决策步骤 `RuleBasedDecider`。

#### `crawling/decisions/chain.py`

把多个决策步骤串起来，形成 `UrlDecisionChain`。

当前实现里主要是单个 `RuleBasedDecider`，但结构已经为未来扩展留好了位置。

### 7. 抓取基础设施

#### `crawling/fetching/base.py`

定义抓取相关的数据结构和协议：

- `FetchResult`
- `FetchAttempt`
- `PageTooLargeError`
- `FetchingStrategy`

#### `crawling/fetching/httpx_fetcher.py`

这是实际使用的 HTTP 抓取实现。

主要能力：

- 同步抓单页
- 异步并发抓多页
- 限制最大并发
- 限制页面最大字节数
- 对错误做分类，例如：
  - `timeout`
  - `invalid_url`
  - `http_status`
  - `request_error`
  - `page_too_large`

这个模块是 orchestrator 抓首页和抓候选页时真正依赖的网络层。

### 8. 运行时与后台持续抓取

#### `runtime/service.py`

这个模块实现后台 runtime 模式。

和 `run_once()` 的区别是：

- `run_once()` 是同步、一次性的 batch
- `CrawlerRuntimeService` 是长生命周期、带 worker 状态的运行器

它负责：

- 启动 / 停止后台抓取线程
- 维护多个 worker 的运行状态快照
- 控制 priority queue 和 normal queue 的公平 claim
- 聚合本次 runtime 的 processed / discovered / failed
- 对外提供 `/internal/runtime/*` 需要的状态

如果你关心“后台一直跑”的逻辑，主要看这里。

#### `runtime/executor.py`

提供一个很薄的线程执行器，用于把 runtime loop 放到后台线程里启动。

#### `contracts/runtime.py`

定义 runtime 对外暴露的数据结构，包括：

- `RuntimeWorkerSnapshot`
- `RuntimeSnapshot`
- `RuntimeAggregate`

### 9. 领域模型与结果结构

#### `domain/`

这个目录放的是 crawler 运行时会频繁传递的小型领域对象：

- `blog_node.py`：当前待抓博客
- `crawl_state.py`：要回写到 persistence 的抓取状态
- `decision_outcome.py`：决策链输出
- `friend_link_edge.py`：发现到的边
- `exceptions.py`：crawler 领域异常

#### `contracts/results.py`

定义同步 crawl 流程里常用的结果结构：

- `BlogCrawlResult`
- `CrawlRunStats`

### 10. 导出与观测

#### `export_service.py`

负责把当前图数据导出到 `export_dir`。

会写出：

- `nodes.csv`
- `edges.csv`
- `graph.json`
- 以及 `graph_projection` 生成的额外快照文件

#### `observability/logger.py`

集中封装 crawler 的日志打点，避免日志格式散落在流程代码中。

#### `utils.py`

一些低层通用工具，例如：

- `clean_text()`
- `text_contains_any()`
- `unique_in_order()`

## 主流程怎么串起来

可以把 crawler 理解为下面这条链路：

```text
crawler.main
  -> CrawlPipeline.run_once()
  -> process_blog_row()
  -> CrawlOrchestrator.crawl_blog()
  -> fetch homepage
  -> discover friend-links pages
  -> fetch candidate pages
  -> extract candidate links
  -> filter / decision chain
  -> repository.upsert_blog + add_edge
  -> mark blog finished
  -> ExportService.write_exports()
```

后台 runtime 模式则是在外面再包一层 worker-pool：

```text
CrawlerRuntimeService
  -> claim waiting blog
  -> pipeline.process_blog_row()
  -> update worker snapshots
  -> aggregate results
```

## Quick Start

这里给两个最实用的启动方式。

### 方式一：启动 persistence-api + crawler 服务

这是最接近真实 split-service 架构的本地方式。

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

然后可以直接调用 crawler 内部接口：

```bash
curl -X POST http://127.0.0.1:8010/internal/crawl/bootstrap
curl -X POST "http://127.0.0.1:8010/internal/crawl/run?max_nodes=2"
curl http://127.0.0.1:8010/internal/runtime/status
```

适用场景：

- 想验证 crawler 服务接口
- 想联调 backend / persistence-api
- 想看 runtime 状态接口

### 方式二：直接跑单次调试脚本

如果你只想快速 debug 单次 `run_once()`，可以使用仓库里的：

- `debug/debug_run_once.py`

它会：

- 强制使用本地 SQLite
- 构建 repository
- 跑 `bootstrap_seeds()`
- 再执行一次 `pipeline.run_once(max_nodes=1)`

直接运行：

```bash
python debug/debug_run_once.py
```

适用场景：

- 不想先启动 persistence-api
- 只想快速追踪单次抓取流程
- 想在 IDE 里对 `run_once()` / `crawl_blog()` 下断点

## 阅读建议

如果你的目标是：

- 看服务入口：先读 `main.py`
- 看同步抓取主流程：先读 `crawling/pipeline.py`
- 看单博客抓取核心：先读 `crawling/orchestrator.py`
- 看友链页发现：先读 `crawling/discovery.py`
- 看候选链接抽取：先读 `crawling/extraction.py`
- 看 URL 过滤规则：先读 `filters.py`
- 看后台持续抓取：先读 `runtime/service.py`

## 与其他服务的关系

`crawler/` 本身不负责最终数据库实现。

在服务运行形态下：

- `crawler.main` 通过 `PersistenceHttpClient` 调用 persistence-api
- persistence-api 再负责真正的数据库读写

所以如果你发现 crawler “没抓到数据”或者“claim 不到 blog”，除了看 crawler 本身，还要联动检查：

- `persistence_api/`
- `shared/http_clients/persistence_http.py`
- `shared/config.py`

## 当前实现特点

当前 crawler 的设计偏向：

- 规则明确
- 流程可调试
- 结果可导出
- runtime 状态可观测

它不是一个无限扩展的通用爬虫框架，而是一个围绕“博客首页 -> 友链页 -> 博客主页链接”这条窄而清晰链路构建的专用 crawler。
