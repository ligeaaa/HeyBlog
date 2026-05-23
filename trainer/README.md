# Trainer

`trainer/` 是 HeyBlog 当前的离线博客二分类训练工作流。它只依赖页面可稳定获得的两类输入：

- `url`
- `title`

目标是在不抓取正文内容的前提下，用轻量、可解释、可快速迭代的 baseline 比较不同特征工程与模型组合。

## 任务定义

- 输入来源：`data/blog-label-training-*.csv`
- 当前标签映射：
  - `blog -> blog`
  - `others -> non_blog`
  - `company -> non_blog`
  - 其他未映射标签 -> `excluded`
- 训练目标：二分类，判断一个 URL + title 样本是否为博客页
- 切分方式：domain-aware 的 `train / val / test`
  - 同一 domain 不会同时出现在多个 split 中

## 工作流

1. `prepare-dataset`
   - 读取人工标注 CSV
   - 规范化 URL
   - 按规范化 URL 聚合重复样本
   - 做标签归并与冲突解析
   - 生成 `train.jsonl` / `val.jsonl` / `test.jsonl`
2. `train`
   - 选择一个 baseline
   - 读取训练 split
   - 抽取特征并训练模型
   - 输出 `model.joblib`、`feature_summary.json`、`train.log`
3. `evaluate`
   - 读取 `test.jsonl`
   - 调用 `predict_proba`
   - 输出 metrics、confusion matrix、误判样本和 markdown 报告
4. `full-run`
   - 串起 `prepare-dataset -> train -> evaluate`
   - 依次跑默认 baseline 集合

### Graph GCN 实验入口

`trainer/graph/` 是隔离的图实验 lane，不改写上面的 URL/title baseline 主流程。它读取 `data/dataset/graph.json` 和 `data/dataset/labels.csv`，只在“图中存在且有人工标签”的节点上做监督训练与评估。

当前 GCN 入口：

```bash
python -m trainer.cli train-gcn --dataset-dir data/dataset
```

输出默认写入 `data/model/gcn/{YYMMDDHHMM}/`，包括：

- `model.pt`
- `config.json`
- `dataset_summary.json`
- `metrics.json`
- `predictions_labeled.csv`
- `report.md`

当前第一版 GCN 使用 URL/title 字符 TF-IDF 作为节点特征，并在导出的友链图上做两层图卷积。评估报告中的指标是 graph-in 指标：只有同时出现在 `labels.csv` 和 `graph.json` 中的节点会进入 train / val / test。

## 特征工程

当前有三条特征路径：

- `structured` 路径：人工设计的数值/布尔特征
- `tfidf` 路径：把 URL 和 title 转成 token 文档，再做稀疏 TF-IDF
- `qwen_embedding_lr` 路径：把 URL、title 和抓取正文 text 拼成指令输入，再用 Qwen embedding 模型生成 dense semantic features

### URL 预处理

在进入特征提取前，数据准备阶段会先对 URL 做规范化，并把同一个规范化 URL 的重复标注聚合到同一个样本上。训练阶段主要使用 `normalized_url`。

### Structured URL Features

结构化 URL 特征来自 [`trainer/features/url_features.py`](/Users/lige/code/HeyBlog/trainer/features/url_features.py)，目前包括：

- 路径结构：
  - `url:path_depth`
  - `url:path_length`
  - `url:is_root_path`
- 查询参数与 host 结构：
  - `url:has_query`
  - `url:subdomain_count`
  - `url:domain_length`
- URL 形态：
  - `url:url_length`
  - `url:hyphen_count`
  - `url:underscore_count`
  - `url:digit_ratio`
- 关键词命中：
  - 对 `blog`、`post`、`article`、`archive`、`tag`、`category`、`about`、`company` 等关键词做布尔命中
  - 关键词会在 host 和 path 上检查

这条路径更偏“显式规则信号”，适合线性模型和树模型快速比较。

### Structured Title Features

结构化 title 特征来自 [`trainer/features/title_features.py`](/Users/lige/code/HeyBlog/trainer/features/title_features.py)，目前包括：

- 标题标准化：
  - Unicode `NFKC`
  - 去首尾空白
  - 转小写
  - 合并连续空白
- 统计特征：
  - `title:missing`
  - `title:length`
  - `title:token_count`
  - `title:avg_token_length`
- 关键词命中：
  - `blog`、`notes`、`journal`、`diary`、`company`、`official`、`studio` 等

### Structured Feature Assembly

结构化 baseline 会把：

- URL 结构化特征
- Title 结构化特征

直接 merge 成一个 `dict[str, float]`，然后交给 `DictVectorizer` 做稀疏向量化。实现位于 [`trainer/features/assemble.py`](/Users/lige/code/HeyBlog/trainer/features/assemble.py)。

### TF-IDF URL Documents

TF-IDF 路径不会直接使用上述数值特征，而是先把 URL 转成 token 文档：

- 字符级 n-gram：
  - 默认 `3-5 gram`
  - 直接对整个 `normalized_url` 做滑窗
- URL token：
  - 从 `netloc`、`path`、`query` 中切词
  - 分词规则兼容字母、数字和中文

最终 URL 文档约等于：

- `url_char_ngrams(normalized_url, 3, 5)`
- `+ tokenize_url(normalized_url)`

### TF-IDF Title Documents

Title 文档路径也来自 [`trainer/features/assemble.py`](/Users/lige/code/HeyBlog/trainer/features/assemble.py)：

- 先做 title 清洗
- 再删除所有非英文、非中文、非数字字符
- 按固定字符块切 token
  - 默认每 `2` 个字符一个 token
- 最后构造词级 n-gram
  - 默认 `1-2 gram`

最终 title 文档约等于：

- `title_word_ngrams(tokenize_title_char_chunks(title, 2), 1, 2)`

### TF-IDF Vectorization

TF-IDF baseline 使用两路独立向量器：

- 一路处理 URL 文档
- 一路处理 title 文档

然后把两路稀疏矩阵横向拼接成最终训练输入。这样做的好处是：

- URL 和 title 保持各自词表
- 可以分别解释两路特征贡献
- 后续更容易替换其中一路的特征工程

### Qwen URL/Title/Text Embeddings

`qwen_embedding_lr` 是可选语义 baseline，不进入默认 `full-run`，因为它会加载 `Qwen/Qwen3-Embedding-0.6B`，运行成本明显高于 TF-IDF。它适合配合带正文的训练 CSV 使用：

```bash
python -m trainer.cli qwen-embedding-run --source-csv data/blog-label-training-2026-04-11-with-text.csv
```

输入模板会包含：

- `URL: <normalized_url>`
- `Domain: <domain>`
- `Title: <title>`
- `Text: <cleaned extracted text>`

每条样本会包装成 Qwen 推荐的 instruction/query 形式。默认最多取 `12000` 个正文字符，再交给 tokenizer 按 `max_length=8192` 截断。一键 pipeline 会为单次运行生成唯一 `run_id`，并将 train/val/test 全量样本的 embedding 保存到 `data/trainer/embeddings/qwen_embedding_lr/<run_id>/`，其中：

- `embeddings.npz` 保存 dense matrix 和 `sample_ids`
- `manifest.json` 保存模型名、输入字段、截断配置和矩阵路径

之后训练阶段只读取本次 pipeline 生成的唯一 manifest，不需要人工复制路径，也不会重新跑 Qwen。训练和评估的 `model.joblib` 也只保存 manifest-backed encoder；预测时按 sample id 从同一份 embedding cache 中取向量。

## 当前支持的模型

所有模型都通过统一的 `train -> predict_proba -> evaluate` 契约接入，注册入口见 [`trainer/models/registry.py`](/Users/lige/code/HeyBlog/trainer/models/registry.py)。

### Structured Logistic Regression

模型名：

- `structured`
- `structured_lr`

输入：

- `DictVectorizer` 处理后的结构化 URL + title 特征

算法：

- `LogisticRegression`
- `solver='liblinear'`
- `class_weight='balanced'`
- `C = 1 / l2_strength`

特点：

- 训练快
- 结果稳定
- 系数可解释，适合查看正负权重

### Structured Linear SVM

模型名：

- `structured_svm`

输入：

- 同 `structured_lr`

算法：

- `SVC(kernel='linear', probability=True, class_weight='balanced')`

特点：

- 常见的稀疏特征强 baseline
- 对结构化布尔/数值特征通常有不错判别力

### Structured Random Forest

模型名：

- `structured_rf`

输入：

- 同 `structured_lr`

算法：

- `RandomForestClassifier`
- 默认 `n_estimators = 200`
- `class_weight='balanced'`

特点：

- 能表达部分非线性特征交互
- `feature_summary.json` 输出的是 feature importance，而不是线性权重
- 只放在 structured 路径上，不放在 TF-IDF 路径上，避免高维稀疏特征导致训练/内存代价过高

### TF-IDF Logistic Regression

模型名：

- `tfidf`
- `tfidf_lr`

输入：

- URL TF-IDF 稀疏矩阵
- Title TF-IDF 稀疏矩阵
- 两者拼接后的稀疏表示

算法：

- `LogisticRegression`

特点：

- 是当前最标准的文本 baseline 之一
- 适合做 URL/title 词面模式学习

### TF-IDF Linear SVM

模型名：

- `tfidf_svm`

输入：

- 同 `tfidf_lr`

算法：

- `SVC(kernel='linear', probability=True, class_weight='balanced')`

特点：

- 经典文本分类 baseline
- 通常适合作为 TF-IDF 路线上的强对照模型

### TF-IDF Complement Naive Bayes

模型名：

- `tfidf_nb`

输入：

- 同 `tfidf_lr`

算法：

- `ComplementNB`
- 默认 `alpha = 1.0`

特点：

- 是常见文本分类基线
- 对类别不均衡和稀疏特征通常有不错鲁棒性
- 需要非负输入，因此放在 TF-IDF 路径上而不是 structured 路径上

### Qwen Embedding Logistic Regression

模型名：

- `qwen_embedding_lr`

输入：

- Qwen embedding dense vector，来源于 `normalized_url + domain + title + text`

算法：

- `LogisticRegression`

特点：

- 能利用正文语义，比只看 URL/title 的 TF-IDF 更可能识别“个人博客、技术笔记、日志、文章列表”等内容信号
- 对正文质量敏感；如果页面 text 主要是导航、页脚或模板噪声，收益会下降
- 不作为默认模型运行，避免常规训练流程下载和加载大模型

## 默认 Full Run 模型集

`full-run` 当前默认执行：

- `structured`
- `structured_svm`
- `structured_rf`
- `tfidf`
- `tfidf_svm`
- `tfidf_nb`

说明：

- 逻辑回归别名 `structured_lr` / `tfidf_lr` 不进入默认 `full-run`
- 这是为了避免和 `structured` / `tfidf` 重复产出两份等价 run

## 命令

准备数据：

```bash
python -m trainer.cli prepare-dataset
```

训练单个模型：

```bash
python -m trainer.cli train --dataset-dir data/trainer/datasets/blog-label-training-2026-04-11-baseline-v1 --model structured_rf
```

`--model` 当前支持：

```text
structured
structured_lr
structured_svm
structured_rf
tfidf
tfidf_lr
tfidf_svm
tfidf_nb
qwen_embedding_lr
```

评估单个模型 run：

```bash
python -m trainer.cli evaluate --run-dir data/model/<model_name>/<YYMMDDHHMM>
```

执行完整流程：

```bash
python -m trainer.cli full-run --source-csv data/blog-label-training-2026-04-11.csv
```

执行完整 Qwen URL/title/text embedding 流程：

```bash
python -m trainer.cli qwen-embedding-run --source-csv data/blog-label-training-2026-04-11-with-text.csv
```

该命令会依次执行：

- `prepare-dataset`
- `build-embeddings`
- `train --model qwen_embedding_lr`
- `evaluate`

单次运行内部只产生一个 embedding manifest，并自动传给训练阶段。

## 输出产物

数据集目录：

- `data/trainer/datasets/<dataset_version>/`
  - `raw_export.csv`
  - `label_resolution.jsonl`
  - `full_supervised.jsonl`
  - `train.jsonl`
  - `val.jsonl`
  - `test.jsonl`
  - `dataset_stats.json`
  - `split_manifest.json`

训练/评估目录：

- `data/model/<model_name>/<YYMMDDHHMM>/`
  - `config.json`
  - `metrics.json`
  - `predictions_test.csv`
  - `confusion_matrix.json`
  - `top_errors.csv`
  - `feature_summary.json`
  - `model.joblib`
  - `train.log`
  - `report.md`

## 解释性产物

`feature_summary.json` 的含义取决于模型类型：

- 线性模型（LR / linear SVM）
  - 输出正向权重和负向权重
  - 有助于看哪些特征更推向 `blog` / `non_blog`
- 随机森林
  - 输出 feature importances
  - 更适合看全局重要性，不适合直接解释正负方向
- Naive Bayes
  - 输出按类别对比后的特征权重摘要

## 依赖

- `numpy`
- `scikit-learn`
- `scipy`
- `torch`
- `transformers`

当前训练代码已经不再依赖自实现的逻辑回归或 TF-IDF 向量器。

## 备注

- `model.joblib` 沿用常见命名，但当前序列化方式保持兼容现有训练/评估流水线
- 如果后续调整标签映射，需要重新执行 dataset prepare 和 downstream runs
