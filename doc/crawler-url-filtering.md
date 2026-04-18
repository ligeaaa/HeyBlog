# HeyBlog 爬虫与 URL 过滤逻辑

## 适合谁看

- 想快速理解当前爬虫真实执行顺序的开发者
- 想定位“为什么某个链接被保留/被过滤”的维护者
- 准备修改 URL 过滤、模型共识、友链发现规则的人

## 建议前置阅读

- [project-structure.md](./project-structure.md)
- [config-reference.md](./config-reference.md)
- [developer-workflows.md](./developer-workflows.md)

## 最后核对源码入口

- [crawler/main.py](../crawler/main.py)
- [crawler/crawling/pipeline.py](../crawler/crawling/pipeline.py)
- [crawler/crawling/orchestrator.py](../crawler/crawling/orchestrator.py)
- [crawler/crawling/discovery.py](../crawler/crawling/discovery.py)
- [crawler/crawling/extraction.py](../crawler/crawling/extraction.py)
- [crawler/filters.py](../crawler/filters.py)
- [crawler/crawling/decisions/chain.py](../crawler/crawling/decisions/chain.py)
- [crawler/crawling/decisions/consensus.py](../crawler/crawling/decisions/consensus.py)
- [crawler/crawling/normalization.py](../crawler/crawling/normalization.py)

## 1. 文档目的

这份文档只描述当前仓库里已经落地的爬虫执行路径，以及 URL 候选链接是如何被筛选、保留和落库的。

重点覆盖：

- crawler 服务的入口和核心依赖
- 单次 `run_once()` 的真实执行链路
- 从首页发现友链页、从友链页抽候选链接的策略
- 确定性 URL 过滤规则
- 多模型负向共识过滤层
- URL 标准化与 blog identity 归一规则
- 与配置项、Docker 运行时模型目录的关系

不覆盖：

- 前端展示层的图谱 UI
- persistence 数据库表结构的完整说明
- trainer 训练流程本身

## 2. 总体架构

当前 crawler 服务是一个独立 FastAPI 进程，由 [crawler/main.py](../crawler/main.py) 提供 HTTP 入口。

它不直接在 web 层连接数据库，而是通过 `PersistenceHttpClient` 调 `persistence-api`。这意味着 crawler 的服务边界是：

- `crawler` 负责抓取、发现、过滤、运行时调度
- `persistence-api` 负责博客、边、状态的持久化

crawler 的两种主要运行方式：

- 同步批处理：`POST /internal/crawl/run`
- 后台持续运行：`POST /internal/runtime/start`

两者底层都依赖同一套抓取实现：

- 同一个 `CrawlPipeline`
- 同一个 `CrawlOrchestrator`
- 同一条 `UrlDecisionChain`

这很重要，因为它保证：

- live crawl 和 runtime crawl 使用一致的 URL 过滤逻辑
- 后续 persistence 侧的规则重扫也可以复用同一条决策链

## 3. 爬虫主流程

### 3.1 入口层

[crawler/main.py](../crawler/main.py) 在启动时会：

- 通过 `Settings.from_env()` 读取环境变量
- 构建 `PersistenceHttpClient`
- 构建 `CrawlPipeline`
- 构建 `CrawlerRuntimeService`

暴露的核心接口有：

- `POST /internal/crawl/bootstrap`
- `POST /internal/crawl/run`
- `GET /internal/runtime/status`
- `GET /internal/runtime/current`
- `POST /internal/runtime/start`
- `POST /internal/runtime/stop`
- `POST /internal/runtime/run-batch`

### 3.2 `run_once()` 批处理流程

[crawler/crawling/pipeline.py](../crawler/crawling/pipeline.py) 里的 `run_once()` 是当前最直接的同步抓取入口。

整体顺序如下：

1. 计算本次最大处理节点数 `max_nodes`
2. 按优先队列公平策略 claim 下一个待抓博客
3. 对每个博客调用 `process_blog_row()`
4. `process_blog_row()` 再调用 `_crawl_blog()`
5. `_crawl_blog()` 把工作交给 `CrawlOrchestrator.crawl_blog()`
6. 每个博客结束后累计 `processed / discovered / failed`
7. 本轮结束后执行 `write_exports()`

### 3.3 队列公平策略

`CrawlPipeline._claim_next_scheduled_blog()` 当前不是简单 FIFO，而是带优先队列公平窗口：

- 优先种子队列优先级更高
- 但不会无限饿死普通 waiting 队列
- 参数 `priority_seed_normal_queue_slots` 控制“处理一个 priority 后，允许多少个 normal queue 项穿插执行”

这套逻辑也被 runtime 模式复用。

## 4. 单博客抓取链路

单个博客的完整抓取逻辑在 [crawler/crawling/orchestrator.py](../crawler/crawling/orchestrator.py)。

`crawl_blog()` 的真实顺序是：

1. 抓取博客首页
2. 从首页提取站点元信息
3. 从首页发现候选友链页
4. 批量抓取这些候选友链页
5. 从每个候选页抽取候选链接
6. 对每个候选链接执行 URL 决策链
7. 对通过的链接做标准化、去重、落库
8. 写入 blog 结果和 edge
9. 将当前源博客标记为 `FINISHED`

抓取成功后，当前源博客会回写：

- `crawl_status=FINISHED`
- `status_code=首页 HTTP 状态码`
- `friend_links_count=本次接受的外链博客数`
- `title`
- `icon_url`

如果超时或异常，则由 `CrawlPipeline._mark_blog_failed()` 标记为 `FAILED`。

## 5. 首页友链页发现逻辑

[crawler/crawling/discovery.py](../crawler/crawling/discovery.py) 只解决一个问题：

“从博客首页推断哪些页面可能是友链页？”

### 5.1 明确发现

它会扫描首页里的所有 `<a>`，结合三类信息判断一个链接是否像“友链目录页”：

- anchor 文本
- 附近结构性上下文文本
- URL path 形态

正向关键词包括：

- `友链`
- `友情链接`
- `blogroll`
- `friend links`
- `friends`
- `links`
- `伙伴`
- `邻居`
- `neighbors`

反向关键词包括：

- `about`
- `archive`
- `contact`
- `feed`
- `github`
- `rss`
- `search`
- `sitemap`
- `tag`
- `resource`

如果命中任一正向信号，就会把该链接作为候选友链页。

### 5.2 Fallback 路径探测

如果首页一个明确候选都没找到，就会回退到固定路径猜测：

- `/links`
- `/friends`
- `/friend-links`
- `/blogroll`
- `/friendlink`

也就是说，即使首页没有显式“友情链接”入口，crawler 仍然会尝试一些常见路径。

## 6. 候选友链页链接抽取逻辑

[crawler/crawling/extraction.py](../crawler/crawling/extraction.py) 在候选页中做的是“抽取链接”，还不负责判断这些链接是不是博客。

### 6.1 如何选容器

它会先挑一批可能的结构容器：

- `main`
- `section`
- `article`
- `aside`
- `div`
- `ul`
- `ol`
- `table`

对每个容器，用以下信号判断它是否像“友链区块”：

- 标题或正文中含有 `友链`、`friends`、`blogroll`、`neighbors`
- `id/class` 中带类似关键词
- 区块里是否存在足够多的外链

负向关键词包括：

- `archive`
- `contact`
- `rss`
- `search`
- `sitemap`

如果多个容器重叠，优先选更深、更具体的容器，避免同一批链接被重复提取。

### 6.2 抽取结果

提取后的标准结果是 `ExtractedLink`，包含：

- `url`：绝对 URL
- `text`：anchor 文本
- `context_text`：容器局部上下文文本

如果没有明确命中的 friend-links 容器，会退化到一个 fallback 容器继续抽取，保证 pipeline 不会因为站点 HTML 形态不标准而完全停住。

## 7. URL 过滤总览

当前 URL 过滤不是单一函数，而是一条决策链，由 [crawler/crawling/decisions/chain.py](../crawler/crawling/decisions/chain.py) 组装。

默认顺序：

1. `RuleBasedDecider`
2. `ModelConsensusDecider`（若启用）

执行语义是：

- 按顺序逐步判断
- 任一步拒绝就立即返回
- 只有所有步骤都通过，链接才会被保留

因此，模型层不会覆盖硬规则层，而是只会进一步过滤硬规则已经允许通过的候选。

## 8. 确定性 URL 过滤规则

[crawler/filters.py](../crawler/filters.py) 是当前最核心的确定性过滤逻辑。

函数入口是 `decide_blog_candidate(url, source_domain, ...)`。

它当前是纯硬规则 accept/reject，不再使用软评分。

### 8.1 接受前必须通过的硬规则

候选链接必须同时满足：

- 是 HTTP(S)
- 不是和源博客同域
- 不命中精确 URL 黑名单
- 不命中 URL 前缀黑名单
- 不命中平台域名黑名单
- 不命中环境变量配置的域名黑名单
- 不命中被拦截的顶级域后缀
- path 必须是根路径风格
- 不能带 query 或 fragment
- 不能是静态资源文件
- 不能命中已知非主页 path

### 8.2 典型拒绝原因

当前内置 reason code 包括：

- `non_http_scheme`
- `same_domain`
- `exact_url_blocked`
- `prefix_blocked`
- `platform_blocked`
- `domain_blocked`
- `blocked_tld`
- `non_root_path`
- `non_root_location`
- `asset_suffix`
- `blocked_path`

全部通过后，返回：

- `accepted=True`
- `reasons=("passed_hard_filters",)`

### 8.3 平台域名黑名单

代码里直接内置了一批平台域名，例如：

- `github.com`
- `twitter.com`
- `x.com`
- `bilibili.com`
- `youtube.com`
- `zhihu.com`
- `weibo.com`
- `medium.com`
- `reddit.com`

这些域名以及其子域名都会被直接拦掉。

### 8.4 顶级域与 path 限制

默认被拦截的顶级域包括：

- `.gov`
- `.gov.cn`
- `.org`
- `.edu`

默认被拦截的 path 包括：

- `/admin`
- `/api`
- `/archive`
- `/archives`
- `/contact`
- `/feed`
- `/login`
- `/register`
- `/rss`
- `/search`

这套规则的核心假设是：

“友情链接目录里的目标，通常应该是目标博客的主页，而不是某篇文章、某个分类页或某个功能页。”

所以当前策略对非根路径非常保守。

## 9. 配置型黑名单

除了代码内置规则，crawler 还支持通过环境变量追加黑名单。

对应配置见 [config-reference.md](./config-reference.md)：

- `HEYBLOG_FRIEND_LINK_DOMAIN_BLOCKLIST`
- `HEYBLOG_FRIEND_LINK_TLD_BLOCKLIST`
- `HEYBLOG_FRIEND_LINK_EXACT_URL_BLOCKLIST`
- `HEYBLOG_FRIEND_LINK_PREFIX_BLOCKLIST`

这些配置会在 `build_url_decision_chain()` 时注入 `RuleBasedDecider`。

也就是说，运行时配置可以扩展拦截面，但不会改变决策链顺序。

## 10. 多模型负向共识逻辑

[crawler/crawling/decisions/consensus.py](../crawler/crawling/decisions/consensus.py) 提供第二层过滤：模型共识。

注意：它不是“模型决定是否保留”，而是“只有所有模型都认为不是博客时才拒绝”。

### 10.1 模型加载方式

模型根目录来自：

- `HEYBLOG_DECISION_MODEL_ROOT`

默认值是：

- `./runtime_resources/models/url_decision/current`

Docker 默认会把它映射为容器内：

- `/app/runtime_resources/models/url_decision/current`

模型目录结构约定为：

- `<model_root>/<model_name>/<run>/model.joblib`

系统会扫描每个模型目录下名称最大的最新 run，并加载其中的 `model.joblib`。

### 10.2 模型投票规则

每个候选 URL 会先被转换成一个 `ConsensusSample`，其中包含：

- `url`
- `normalized_url`
- `domain`
- `title`

这里的 `title` 不是页面 title，而是一个“就地构造的标题替代值”，优先级是：

1. `link_text`
2. `context_text`
3. `normalized.domain`

之后每个模型都会输出一个 `predict_proba([sample])` 概率。

最终规则：

- 如果没有可用模型：放行，reason=`model_consensus_skipped_no_models`
- 如果所有可用模型都投 `non_blog`：拒绝，reason=`model_consensus_all_non_blog`
- 只要有任意一个模型投 `blog`：保留，reason=`model_consensus_kept`

也就是说，这是一个严格负向共识，而不是多数投票接受。

### 10.3 为什么这样设计

当前设计偏保守，目标是：

- 不要因为某一个模型过于激进就过滤掉潜在博客
- 只在“所有模型都明确不认同”时才拒绝

因此模型层更像一个“补充拦截器”，不是主导分类器。

## 11. URL 标准化与 identity 归一

这部分在 [crawler/crawling/normalization.py](../crawler/crawling/normalization.py)。

需要区分两层：

- `normalize_url()`：轻量标准化，直接影响 crawler 去重和落库
- `resolve_blog_identity()`：更强的 homepage identity 归一，服务于站点级归并

### 11.1 `normalize_url()`

当前会做：

- 自动补默认 scheme 为 `https`
- host 转小写
- 空 path 归一成 `/`
- 非根路径去掉末尾 `/`
- 去掉 tracking 参数

默认移除的 tracking 参数包括：

- `utm_source`
- `utm_medium`
- `utm_campaign`
- `utm_term`
- `utm_content`
- `spm`
- `ref`

这一层不会主动判断“两个 URL 是否属于同一个站点首页”，它的目标只是给 crawler 一个稳定、轻量的去重 key。

### 11.2 `resolve_blog_identity()`

这一层会进一步尝试把多个等价首页 URL 合并成一个 blog identity。

当前规则包括：

- 忽略 `http/https` scheme 差异
- 折叠默认首页路径，如 `/index.html`
- 对 homepage-like URL 折叠安全 host alias，如 `www`、`blog`
- 对特定可推断的租户子域名执行 collapse

identity 输出里会记录：

- `canonical_host`
- `canonical_path`
- `canonical_url`
- `identity_key`
- `reason_codes`
- `ruleset_version`

当前规则版本号是：

- `2026-04-07-v5`

## 12. 过滤结果如何落库

在 [crawler/crawling/orchestrator.py](../crawler/crawling/orchestrator.py) 里，候选链接通过决策链后会进入 `_store_page_links()`。

具体顺序是：

1. 再次对链接执行 `normalize_url()`
2. 按 `normalized.normalized_url` 做跨候选页去重
3. `upsert_blog(url, normalized_url, domain)`
4. 建立 `FriendLinkEdge`
5. 调用 `repository.add_edge(...)`

这说明当前去重粒度是：

- 单次 crawl 过程中：以 `normalized_url` 去重
- 持久化层：再由 repository 的 upsert 逻辑兜底

## 13. 超时与大页面处理

爬虫不仅过滤 URL，也对页面抓取本身做预算限制。

关键配置可结合 [config-reference.md](./config-reference.md) 和
[shared/config.py](../shared/config.py) 一起看：

- `HEYBLOG_BLOG_CRAWL_TIMEOUT_SECONDS`
- `HEYBLOG_CANDIDATE_PAGE_FETCH_CONCURRENCY`
- `HEYBLOG_MAX_FETCHED_PAGE_BYTES`

语义是：

- 一个博客的整次 crawl 有总超时预算
- 候选页可并发抓取
- 单页超出字节上限会触发 `PageTooLargeError`
- 若候选页超大，当前 blog 会被标记为 `FAILED`

因此“没有抓到友链”不一定是过滤规则问题，也可能是：

- 首页超时
- 候选页超时
- 页面过大
- 页面提取阶段未命中 friend-links 容器

## 14. 当前设计的真实取向

当前 crawler 的整体风格是保守、确定性优先：

- 先尽量发现友链目录页
- 再从目录页里提取所有候选链接
- 然后用严格的 homepage 硬规则筛掉明显非博客目标
- 最后再用多模型负向共识做补充拦截

这意味着它偏向：

- 少抓错明显非博客平台
- 少把深层 URL 当成博客主页
- 不让模型直接主导链接接受

也意味着当前已知限制包括：

- 对“博客主页不在根路径”的站点不友好
- 对“友情链接页面结构非常奇怪”的站点依赖 fallback
- 对“非博客主页但看起来像根域名”的站点仍可能漏拦

## 15. 调试建议

如果你想排查一个链接为什么没进图里，建议按这个顺序看：

1. 看首页是否发现了候选友链页：`crawling/discovery.py`
2. 看候选页是否抽出了那个链接：`crawling/extraction.py`
3. 看 URL 是否被硬规则拒绝：`filters.py`
4. 看是否被模型共识拒绝：`decisions/consensus.py`
5. 看是否因超时/页面过大在更早阶段失败：`fetching/httpx_fetcher.py`
6. 看持久化层最终是否 `upsert_blog` / `add_edge`

如果只是想快速调试一次真实流程，可以优先从仓库里的：

- `debug/debug_run_once.py`

入手。

## 16. 相关文档

- [crawler/README.md](../crawler/README.md)
- [config-reference.md](./config-reference.md)
- [project-structure.md](./project-structure.md)
- [developer-workflows.md](./developer-workflows.md)
