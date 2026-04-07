# URL + Title 博客分类离线训练设计详案

## 1. 摘要

本文档定义 HeyBlog 首轮“URL + Title 是否为博客”的离线二分类训练方案。该方案严格限定在已经过人工标注的样本之上，只使用 `url` 与 `title` 两类输入信号，不使用图结构、不使用 GNN、不使用在线推理链路。目标不是一次性构建最终模型，而是以最短验证路径回答三个核心问题：

1. 当前人工标注数据是否已经足以训练一个有用的博客分类器。
2. 仅依赖 `url + title` 这两类轻量信号，模型能达到什么质量上限。
3. 下一阶段的主要瓶颈究竟是样本量、标签质量，还是特征表达能力。

在工程定位上，本方案是一个新增顶层 `trainer/` 的离线 workflow package，而不是服务化系统的一部分。它的核心产物是可复现实验、稳定数据切分、基线模型指标、误差分析和后续扩展决策依据。

## 2. 问题定义

### 2.1 任务表述

给定一个样本 `x = (url, title)`，预测其二分类标签 `y ∈ {blog, non_blog}`。

更形式化地说，我们希望学习一个映射函数：

`f(url, title) -> p(blog | url, title)`

其中输出是博客概率，最终可按阈值转换为离散标签。

### 2.2 本轮范围

本轮只包含：

- 已人工标注样本的监督学习
- 二分类标签规整
- `train / val / test` 数据划分
- 至少两个轻量 baseline
- 离线评估与误差分析

本轮明确不包含：

- GNN
- 图结构特征
- 半监督学习
- 在线服务部署
- 爬虫流程接入实时判定

## 3. 数据来源与字段边界

### 3.1 数据表

监督样本来自以下持久化表：

- `blogs`
- `blog_label_tags`
- `blog_label_assignments`

根据当前 ORM 定义，[persistence_api/models.py](/Users/lige/code/HeyBlog/persistence_api/models.py) 中 `BlogModel` 已包含：

- `url`
- `normalized_url`
- `domain`
- `title`
- `crawl_status`

标签体系采用独立多标签结构，不污染 `blogs` 主表：

- `BlogLabelTagModel`
- `BlogLabelAssignmentModel`

### 3.2 样本选择边界

当前人工标注台候选默认只来自 `crawl_status == FINISHED` 的 blog，相关查询逻辑位于 [persistence_api/repository.py](/Users/lige/code/HeyBlog/persistence_api/repository.py)。因此，首轮训练数据也应保持这一边界，避免混入抓取未完成、字段缺失更严重、语义不稳定的中间状态节点。

### 3.3 样本最小字段

每个监督样本至少应包含：

- `blog_id`
- `url`
- `normalized_url`
- `domain`
- `title`
- `raw_labels`
- `binary_label`
- `label_resolution`

其中：

- `raw_labels` 是该 blog 当前命中的所有人工标签
- `binary_label` 是最终二分类结果
- `label_resolution` 记录该样本是 `mapped`、`excluded` 还是 `conflict_review`

## 4. 标签体系与二分类映射

### 4.1 原始标签语义

当前系统中的标签是多标签、用户可扩展的，因此原始标签集合不天然等价于严格二分类。训练前必须先定义冻结的映射规则，否则实验不可复现，指标也不可比较。

### 4.2 首轮推荐映射

推荐首轮先采用保守映射：

- `blog` -> `blog`
- `company` -> `non_blog`
- `others` -> `non_blog`
- 其他标签 -> `excluded`

对于多标签样本，采用如下决策：

- 只命中 `blog`：记为 `blog`
- 只命中 `company` / `others`：记为 `non_blog`
- 同时命中 `blog` 和任一 `non_blog` 标签：记为 `conflict_review`
- 只命中未纳入首轮映射的标签：记为 `excluded`
- 完全无标签：不进入监督数据集

### 4.3 为什么要显式保留 `excluded` 与 `conflict_review`

这是首轮方案的关键约束。很多训练流程会直接把“解释不了的标签”静默丢弃，但这里不应该这样做，因为这会掩盖真实数据质量问题。

保留这两类计数有三个目的：

1. 让我们知道当前标签体系与二分类任务的贴合程度。
2. 让后续标注策略可以针对冲突样本单独修复。
3. 防止训练集被无声污染，导致指标表面好看但语义不稳。

### 4.4 标签映射产物

建议导出一份显式的标签解析结果表，例如 `dataset_manifest.json` 或 `label_resolution.jsonl`，至少记录：

- `blog_id`
- `raw_labels`
- `resolved_binary_label`
- `resolution_reason`

## 5. 数据预处理设计

### 5.1 总体原则

预处理要服务于三个目标：

1. 保留 URL 结构本身的判别信息
2. 降低训练输入的噪声和稀疏性
3. 保持可解释性与可复现性

因此，首轮不追求复杂 NLP，而是以“结构化 URL 特征 + 轻量文本清洗”为主。

### 5.2 URL 预处理

首轮应优先使用 `normalized_url`，当其缺失或不可信时才回退到 `url`。推荐步骤如下：

1. 统一小写处理 scheme、host 和路径中的英文字母。
2. 去除 URL 末尾无意义分隔符，例如冗余 `/`。
3. 去除 fragment。
4. 对 query 参数采用保守策略：
   - 默认不整体保留原始 query
   - 仅统计是否存在 query、query 键数量等结构特征
5. 拆解 URL 为：
   - scheme
   - subdomain
   - registered domain
   - suffix / TLD
   - path segments
6. 生成标准化 token 串，用于 TF-IDF 或词袋。

### 5.3 URL token 化建议

URL token 化不是简单按 `/` 切分，而是应同时保留层级与语义片段。推荐多层切分：

1. host 级：
   - `www.example.com` -> `www`, `example`, `com`
2. path 级：
   - `/blog/2024/hello-world` -> `blog`, `2024`, `hello`, `world`
3. 分隔符级：
   - 再按 `-`, `_`, `.`, `~` 做细粒度切分

同时建议保留少量结构 token，例如：

- `PATH_DEPTH_0`
- `PATH_DEPTH_1`
- `HAS_QUERY`
- `IS_ROOT_PATH`

这样可以让线性模型既看到语义 token，也看到结构轮廓。

### 5.4 URL 结构特征

推荐首轮至少构造以下手工结构特征：

- `path_depth`
- `path_segment_count`
- `is_root_path`
- `has_query`
- `has_fragment`
- `subdomain_count`
- `url_length`
- `domain_length`
- `path_length`
- `digit_ratio`
- `hyphen_count`
- `underscore_count`
- `contains_blog_keyword`
- `contains_post_keyword`
- `contains_article_keyword`
- `contains_archive_keyword`
- `contains_tag_or_category_keyword`
- `contains_feed_keyword`
- `contains_about_or_company_keyword`

其中关键词特征应只作为弱信号，不能替代整体模型判断。

### 5.5 Title 预处理

Title 是当前唯一文本语义输入，但它往往噪声较大，因此建议做轻量规范化：

1. 去除前后空白
2. Unicode 规范化
3. 连续空格折叠
4. 保留大小写不敏感语义，默认统一小写
5. 不做过重的 stemming / lemmatization
6. 缺失 title 不填充伪内容，而是保留为空并生成缺失标记特征

### 5.6 Title 特征

推荐提取两类 title 特征：

1. 文本特征
   - unigram / bigram TF-IDF
   - title token count
   - average token length
2. 结构特征
   - `title_missing`
   - `title_length`
   - `title_has_blog_keyword`
   - `title_has_company_keyword`
   - `title_has_archive_keyword`

### 5.7 缺失值处理

对于缺失值，不建议做“语义补全”，而是做显式缺失建模：

- `title is None` -> 空字符串 + `title_missing = 1`
- URL 缺失属于数据错误，应直接剔除并进入数据质量报告
- `domain` 缺失原则上不应出现，若出现应标记为导出失败

### 5.8 去重策略

由于 `normalized_url` 在 `blogs` 表上应唯一，样本层面一般不会出现同 URL 重复。但在训练导出时仍需检查：

1. 是否存在多个 blog 共享相同 `domain + path` 语义但标签冲突
2. 是否存在重扫或历史清洗后残留的标签重复
3. 是否存在相同 `normalized_url` 在导出视图中重复出现

建议导出前增加唯一性断言：

- `normalized_url` 唯一
- 每个 `blog_id` 在监督集最多出现一次

## 6. 数据集构建

### 6.1 监督样本生成流程

完整流程建议如下：

1. 从 `blogs` 中选出 `crawl_status = FINISHED` 的样本
2. 左连接标签分配表与标签定义表
3. 聚合同一 `blog_id` 的所有标签
4. 执行标签映射
5. 过滤掉 `excluded` 与 `conflict_review`
6. 产出监督样本清单
7. 生成特征输入和 split 清单

### 6.2 数据集导出文件

建议至少生成以下文件：

- `dataset/full_supervised.jsonl`
- `dataset/train.jsonl`
- `dataset/val.jsonl`
- `dataset/test.jsonl`
- `dataset/label_resolution.jsonl`
- `dataset/split_manifest.json`

### 6.3 导出文件字段建议

每行样本建议至少包含：

- `blog_id`
- `normalized_url`
- `raw_url`
- `domain`
- `title`
- `binary_label`
- `split`
- `title_missing`
- `raw_labels`

## 7. 数据划分方法

### 7.1 划分目标

数据划分的核心目标不是平均分配样本数，而是逼近未来真实泛化场景。对于 URL 分类任务，最容易发生的数据泄漏来自同一 domain 的模板相似性。因此，本任务默认不使用裸随机切分，而使用按 `domain` 分组的切分策略。

### 7.2 推荐默认比例

- `train`: 70%
- `val`: 15%
- `test`: 15%

若总样本量较小，可退化为：

- `train`: 80%
- `val`: 10%
- `test`: 10%

### 7.3 分组切分原则

推荐把 `domain` 视为 group，确保同一 domain 只出现在一个 split 中。这样做的原因是：

1. 同站点 URL 模板往往高度一致
2. title 风格通常也高度重复
3. 如果 train/test 共享 domain，指标会明显乐观偏高

### 7.4 分组分层切分

仅按 domain 分组可能导致类分布失衡，因此推荐采用“group-aware stratification”的近似策略：

1. 先统计每个 domain 下的 `blog` / `non_blog` 数量
2. 按 domain 样本量从大到小排序
3. 采用贪心分配，把每个 domain 分配到当前最能平衡类分布的 split
4. 固定随机种子，确保可复现

如果后续实现中使用现成的 grouped stratified splitter，也应把随机种子、版本与失败回退策略记录到 manifest 中。

### 7.5 极端 domain 处理

需要单独关注两类 domain：

1. 超大 domain
   - 单个 domain 样本数极大，会主导某一 split
2. 极稀有 domain
   - 只出现 1 条样本，且类别分布偏斜

建议在导出报告中单独展示：

- top domains by sample count
- each split 的 domain 数量
- each split 的类分布

### 7.6 重复实验稳定性

除了固定主 split 外，建议后续补充：

- 多随机种子重复实验
- 或基于 domain 的 repeated group split

但首轮只要求一个稳定可复现的官方 split。

## 8. 模型架构设计

### 8.1 设计原则

首轮 baseline 必须满足：

- 小样本可训练
- 可解释
- 训练快
- 便于定位失败模式

因此推荐至少保留两个层次的 baseline。

### 8.2 Baseline A：结构特征 + 线性分类器

#### 8.2.1 输入

- URL 结构特征
- URL keyword 指示特征
- title 的基本统计特征
- title 缺失标志

#### 8.2.2 模型

推荐逻辑回归为默认第一基线：

- 优点是输出概率稳定
- 权重可解释
- 对稀疏和稠密特征拼接都友好

备选可用线性 SVM，但不作为默认，因为概率校准和阈值分析不如逻辑回归直接。

#### 8.2.3 作用

这个 baseline 用来回答：

- URL 结构本身是否已经很强
- 少量可解释规则信号是否足以覆盖主流样本
- 缺失 title 时模型是否仍能维持基本可用

### 8.3 Baseline B：TF-IDF(`url + title`) + 线性分类器

#### 8.3.1 输入

构造两条文本通道：

- `url_text`: 标准化后的 URL token 序列
- `title_text`: 轻量清洗后的 title token 序列

推荐做法：

- URL 与 title 分开建 TF-IDF
- 最后做特征拼接

而不是简单拼成一个字符串。因为二者分布差异明显，分开向量化更利于调参与解释。

#### 8.3.2 向量化建议

- URL：字符 n-gram 或 token n-gram 都可尝试
- Title：word unigram / bigram 为主
- 稀疏矩阵可直接输入逻辑回归

推荐首轮配置：

- URL：char n-gram `(3, 5)` 或 token unigram/bigram 二选一
- Title：word unigram + bigram
- `min_df` 取较小值，避免小样本过度裁剪

#### 8.3.3 模型

仍推荐逻辑回归作为首选，因为它：

- 与 TF-IDF 搭配成熟
- 易于解释高权重 token
- 训练稳定

### 8.4 可选 Baseline C：轻量树模型

如果 Baseline A/B 完成后仍希望增加一个非线性对照组，可引入轻量树模型，但只吃手工结构特征与少量聚合文本特征，不直接吃超高维 TF-IDF 稀疏矩阵。

这一 baseline 不是首轮必需，只作为扩展选项。

### 8.5 为什么不在首轮使用深层神经网络

原因并不是“神经网络一定差”，而是当前问题还处于样本量与任务定义验证阶段。过早上更复杂的模型会带来：

- 调参成本上升
- 可解释性下降
- 对数据噪声更不透明
- 很难判断改进来自模型还是偶然拟合

## 9. 训练策略

### 9.1 类别不平衡处理

如果 `blog` 与 `non_blog` 数量存在偏斜，推荐优先使用：

- class weight
- 阈值后调优

而不是盲目过采样。原因是本任务样本还不大，过采样容易放大少数 domain 模板。

### 9.2 正则化

对于逻辑回归，首轮应显式比较：

- L2 正则
- 不同 `C` 值

这是最重要的一组轻量超参数。

### 9.3 阈值选择

评估阶段不要只看默认 `0.5`。建议在 validation 集上搜索阈值，并记录：

- 最优 F1 阈值
- 在高 precision 约束下的阈值
- 在高 recall 约束下的阈值

这样后续如果模型用于“候选筛选”或“保守自动判定”，可以有不同 operating point。

### 9.4 训练可复现性

每次训练必须记录：

- 数据导出版本
- 标签映射版本
- split 随机种子
- 模型超参数
- 训练时间
- 代码 commit 或工作区快照

## 10. 评估指标与实验协议

### 10.1 必报指标

首轮报告至少包含：

- Precision
- Recall
- F1
- PR-AUC
- Confusion Matrix

不建议只报 Accuracy，因为二分类在类别不平衡时很容易产生误导。

### 10.2 分层分析

除总体指标外，建议至少补充以下切片：

- `title_missing = 1` 与 `title_missing = 0`
- root path 与 deep path
- 大 domain 与小 domain
- `blog` 类错误样本
- `non_blog` 类错误样本

### 10.3 错误分析

误差分析应输出至少两类样本：

- false positives
- false negatives

每条记录建议包含：

- `blog_id`
- `normalized_url`
- `domain`
- `title`
- `gold_label`
- `pred_label`
- `pred_score`
- `raw_labels`

### 10.4 推荐实验矩阵

首轮建议实验矩阵如下：

1. Baseline A：结构特征 + Logistic Regression
2. Baseline B1：URL TF-IDF + Logistic Regression
3. Baseline B2：URL TF-IDF + Title TF-IDF + Logistic Regression
4. Ablation：仅 URL
5. Ablation：仅 Title
6. Ablation：不按 domain 分组的随机切分

其中第 6 项不是正式结果，而是用于量化泄漏带来的乐观偏差。

## 11. 结果解读框架

### 11.1 怎样判断“可以继续”

满足以下条件时，可进入下一阶段实现或批量打分：

1. 指标在 domain-aware test 上稳定优于弱规则基线
2. false positive / false negative 有清晰模式，而不是完全随机
3. title 缺失样本虽然更难，但仍保有基本可分性
4. 错误主要集中在可解释的语义边界，而不是数据管线错误

### 11.2 怎样判断“优先补标签”

若出现以下情况，应优先扩充标注，而不是继续堆模型：

- validation / test 波动很大
- 不同随机种子结果差异明显
- 大量样本落入 `excluded` 或 `conflict_review`
- 主要误差来自标签语义混乱

### 11.3 怎样判断“优先补特征”

若数据规模已经基本够用，但错误集中在：

- title 为空时严重退化
- 公司主页与博客首页混淆严重
- URL 结构相似但语义不同的页面频繁误判

则说明可以考虑在第二阶段增加更细粒度文本特征、页面级信号或其他非图特征。

## 12. 标注规模建议

### 12.1 起步阶段

- 总样本量：`200 - 300`

适合：

- 跑通全流程
- 验证 split 与导出逻辑
- 得到初步 baseline

不足：

- 指标方差大
- 容易被少量 domain 主导

### 12.2 第一版实用阶段

- 总样本量：`800 - 1500`

这是首轮最推荐区间。原因是：

- 已经足以支撑按 domain 分组切分
- 误差分析更有代表性
- baseline 能较稳定比较

### 12.3 较稳阶段

- 总样本量：`2000+`

适合：

- 更可靠地评估泛化
- 更有把握地比较多个模型
- 为下一阶段更复杂方案提供足够支撑

## 13. 建议的工程落地结构

推荐在仓库顶层新增：

- `trainer/dataset_export.py`
- `trainer/label_mapping.py`
- `trainer/features.py`
- `trainer/splits.py`
- `trainer/models/baseline_structural.py`
- `trainer/models/baseline_tfidf.py`
- `trainer/evaluation.py`
- `trainer/main.py`

职责划分如下：

- `dataset_export.py`：从 `persistence_api` 拉取并导出监督样本
- `label_mapping.py`：冻结标签映射规则
- `features.py`：URL/title 清洗与特征工程
- `splits.py`：domain-aware split
- `models/*`：训练与保存 baseline
- `evaluation.py`：指标、错误样本、报告生成
- `main.py`：统一 CLI 入口

## 14. 制品与输出格式

每次正式实验建议在统一输出目录下保存：

- `run_config.json`
- `dataset_stats.json`
- `split_stats.json`
- `metrics.json`
- `confusion_matrix.json`
- `error_samples.jsonl`
- `feature_importance.json` 或高权重 token 导出
- 模型文件

这样后续对比实验不会只剩一张截图或口头结论。

## 15. 主要风险与防错措施

### 15.1 标签语义漂移

风险：

- 标签体系是可扩展多标签，后续新增标签可能改变训练语义边界

措施：

- 首轮冻结映射表并版本化

### 15.2 数据泄漏

风险：

- 同域名样本跨 split 导致虚高指标

措施：

- 默认 domain-aware split
- 报告每个 split 的 domain 覆盖

### 15.3 Title 缺失带来的质量波动

风险：

- 某些 blog title 缺失或质量差，导致模型过分依赖 URL

措施：

- 单独报告 `title_missing` 子集表现

### 15.4 样本量不足

风险：

- baseline 指标不稳定，容易误判模型方向

措施：

- 报告样本规模区间
- 不对小样本阶段结果做过度结论

## 16. 结论

HeyBlog 当前最合理的第一步不是构建复杂图模型，而是围绕已人工标注的 `url + title` 样本，建立一套严谨、可复现、强约束的离线二分类训练流程。只要这一步做扎实，我们就能清楚回答：

- 现有标注是否够用
- 轻量模型的上限在哪里
- 后续应该优先补标签、补特征，还是再讨论更复杂模型

这份详案的意义，不是为了把 baseline 写得“看起来高级”，而是为了让后续每一条实现、每一次实验和每一个性能判断，都有清楚的数据边界与验证合同。
