# 博客分类模型设计

## 背景

旧版模型主要依赖 URL 和 title，crawler runtime 里的模型共识还会丢弃友链锚文本和局部上下文，导致模型只能根据很少的表面信号判断候选是否像博客。这个设计把分类信号扩展到 URL、title、页面正文/HTML、友链上下文和图结构，并保留当前 sklearn/runtime 序列化契约。

## 稳定博客要素

真实博客页面和网页分类研究中反复出现的稳定信号包括：

- 订阅入口：`rss`、`atom`、`feed`、`订阅`。RSS 2.0 规范把 RSS 定义为 Web 内容聚合格式，Atom RFC 4287 也面向 Web syndication，因此 feed 链接、订阅文案、`application/rss+xml` / `application/atom+xml` link 标签是强博客/内容流信号。
- 内容组织：`archive`、`归档`、`tag`、`category`、`标签`、`分类`。RSS item 和 Atom entry 都支持 category，博客系统也常用归档页和标签页组织连续发布内容。
- 内容对象：`post`、`article`、`entry`、`文章`、`日志`、日期列表。Schema.org 明确定义 `Blog` 和 `BlogPosting`，其中 blog post 是 blog 的组成内容；microformats 的 `h-entry` 也常用于可聚合的 blog posts。
- 交互与个人站：`comment`、`reply`、`留言`、`about me`、`关于我`
- 社交链接：`friend links`、`blogroll`、`友链`、`友情链接`
- 语义 HTML：`h-entry`、`h-feed`、`h-card`、`dt-published`、`p-author`、`rel-tag`。Microformats 文档说明 `h-entry` 常用于将 blog posts 这类内容嵌入 HTML，MDN 也把 `h-card`、`h-entry`、`h-feed` 作为 microformats root class 示例。
- 负向信号：`company`、`product`、`pricing`、`careers`、`privacy policy`、`公司`、`产品`、`招聘`

## 相关方法

- URL 分类通常使用 lexical URL 特征：host/path/query token、字符 n-gram、长度、数字比例、路径深度、关键词。URLNet 进一步说明 CNN 可以同时学习 URL 字符级和词级表示，缓解纯手工特征在未见 URL token 上泛化不足的问题。
- 网页分类通常融合 title、正文、anchor text、DOM/meta/link 标签和站内外链接结构。对本项目而言，source page 的 anchor/context 是 target URL 在尚未抓取前最便宜的语义证据，应该进入 runtime sample，而不是只看 URL 字符串。
- PLM-GNN 一类网页分类方法把页面自然语言文本、HTML DOM 结构和 GNN 结合起来，说明“文本语义 + 页面结构图”是更强方向；但它也意味着必须先保证 split 和 overlap 可靠，否则复杂网络会只放大数据泄漏或边噪声。
- 文本/图混合模型不应替代消融。当前 HeyBlog 图边主要来自友链发现，完整边、self-loop、edge-dropout 的对比显示边本身未稳定增益，所以下一步应优先做 edge quality、community holdout、stacking/label propagation 对照，而不是单纯加深 GCN。

## 参考资料

- RSS Advisory Board, RSS 2.0 Specification: https://www.rssboard.org/rss-specification
- IETF RFC 4287, The Atom Syndication Format: https://www.rfc-editor.org/rfc/rfc4287
- Schema.org `Blog`: https://schema.org/Blog
- Schema.org `BlogPosting`: https://schema.org/BlogPosting
- Microformats `h-entry`: https://microformats.org/wiki/h-entry
- MDN, Using microformats in HTML: https://developer.mozilla.org/en-US/docs/Web/HTML/Guides/Microformats
- Le et al., “URLNet: Learning a URL Representation with Deep Learning for Malicious URL Detection”: https://arxiv.org/abs/1802.03162
- “PLM-GNN: A Webpage Classification Method based on Joint Pre-trained Language Model and Graph Neural Network”: https://arxiv.org/abs/2305.05378

## 当前落地

代码落点：

- `trainer/features/page_features.py`：新增页面/上下文博客语义特征。
- `trainer/features/assemble.py`：结构化模型合并 URL、title、page/context；TF-IDF title lane 追加 page signal tokens。
- `trainer/models/hybrid_mlp.py`：新增融合结构化 + URL TF-IDF + title/page TF-IDF 的两层 MLP。
- `trainer/pipelines/train_baseline.py`：训练后用 validation split 自动选择 F1 最优阈值，并写入模型对象供 runtime 使用。
- `crawler/crawling/decisions/base.py`、`crawler/crawling/orchestrator.py`、`crawler/crawling/decisions/consensus.py`：模型共识样本现在携带 anchor text 和友链区块 context。
- `crawler/crawling/decisions/consensus.py`、`shared/config.py`：runtime 共识支持 `weighted_average`、`majority_blog`、`any_blog` 三种策略，默认按模型 `metrics.json` 中的 F1/PR-AUC/accuracy 加权，避免旧弱模型用一票保留稀释新模型收益。
- `trainer/constants.py`：`unknown`、`other`、`company`、`others` 都映射为 `non_blog`。

## 真实评估

数据集：

- Source: `data/blog-label-training-2026-04-11-with-text.csv`
- Prepared: `data/trainer/datasets/blog-classification-redesign-20260523`
- Supervised records: `2376`
- Label counts: `blog=651`, `non_blog=1725`
- Split: domain-aware `70/15/15`

对比结果：

| Model | Run | Threshold | Precision | Recall | F1 | PR-AUC | Accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `tfidf_svm` | `data/model/tfidf_svm/2605231457` | `0.639242` | `0.882979` | `0.864583` | `0.873684` | `0.933002` | `0.932773` |
| `hybrid_mlp` | `data/model/hybrid_mlp/2605231500` | `0.250145` | `0.815534` | `0.875000` | `0.844221` | `0.872978` | `0.913165` |
| `structured_rf` | `data/model/structured_rf/2605231453` | `0.5` | `0.888889` | `0.750000` | `0.813559` | `0.904690` | `0.907563` |
| runtime `weighted_average` consensus | `runtime_resources/models/url_decision/current` | `0.4` | `0.904255` | `0.885417` | `0.894737` | `0.929570` | `0.943978` |

结论：

- 第一阶段最适合作为 runtime 主力的是增强后的 `tfidf_svm`，它在 F1、PR-AUC、accuracy 上都优于当前 MLP。
- 发布后的 runtime 多模型 `weighted_average` 共识用 validation split 选择阈值 `0.4` 后，在 test split 上 F1 达到 `0.894737`，高于单个 `tfidf_svm`，因此当前 runtime 默认使用该策略和阈值。
- `hybrid_mlp` 证明了非线性融合 lane 可以接入现有训练/评估/runtime 契约，但当前结构没有超过强稀疏 SVM。
- 自动阈值选择比固定 `0.5` 更适合当前不平衡数据，`tfidf_svm` 的 precision/recall 更均衡。

## 下一步

1. 增强后的 `tfidf_svm` 已通过 `trainer.cli publish-runtime-model` 发布到 `runtime_resources/models/url_decision/current/tfidf_svm/2605231457`，crawler consensus 能加载其 validation-selected threshold `0.639242`。runtime 默认共识已改成 `weighted_average`，会用 `metrics.json` 指标让强模型获得更高权重，并采用 validation-selected threshold `0.4`。下一步是小规模真实 crawler smoke，并观察是否还需要清理旧 model family。
2. 继续 graph/text fusion，但先做消融和 split 修正：当前 residual GCN（`data/model/gcn/2605231511`）虽然加入了 URL/title/metadata TF-IDF、结构化页面信号、图度数和 residual message passing，测试 F1 只有 `0.795181`、PR-AUC `0.882051`，低于增强 `tfidf_svm`。Edge ablation 显示 `self_loop` F1 `0.797688`，`dropout 0.5` F1 `0.805755`，说明完整 friend-link 边没有稳定正增益，边噪声需要单独建模。`evaluate-graph-runtime-overlap` 对当前 runtime test 与 GCN test 的正式 overlap 检查只有 `16` 条，低于融合门槛 `50`，不能支撑可信 stacking；下一步要先统一 split 或输出同一 universe 的 runtime/GCN out-of-fold prediction。
3. 为 target homepage fetch 后的二阶段判定设计缓存，避免只依赖 source page 的 anchor/context。
4. 扩展标注体系，把 `unknown` 样本单独跟踪，用于主动学习和人工复审。
