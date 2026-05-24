# GCN Blog Classification

## 1. 目标

这份文档说明 HeyBlog 当前第一版 GCN 图神经网络分类实验。它的目标是：

- 在已爬取出的博客友链图上做节点分类。
- 判断一个图中节点是否是个人博客。
- 给出 graph-in 评估结果，也就是只评估同时出现在 `graph.json` 和 `labels.csv` 中的节点。

当前实现是一个离线实验入口，不是线上 crawler 决策链路的一部分。

## 2. 输入数据

默认入口读取：

- `data/dataset/graph.json`
- `data/dataset/labels.csv`

`graph.json` 结构：

```json
{
  "nodes": [],
  "edges": []
}
```

节点来自 Docker Postgres 卷导出的完整 graph snapshot。边表示从一个 blog 节点指向另一个 blog 节点的 friend-link 关系。

`labels.csv` 结构：

```csv
url,title,label
https://example.com/,Example,blog
```

标签映射沿用现有 trainer 规则：

- `blog -> blog`
- `company -> non_blog`
- `others -> non_blog`
- 其他标签暂不进入监督训练

当前导出的完整图规模：

- graph nodes: `18,648`
- graph edges: `46,836`
- labeled rows: `2,373`
- graph-in labeled nodes: `788`

## 3. GCN 原理

GCN，全称 Graph Convolutional Network，用来在图结构上做表示学习。普通文本分类只看一个样本自己的特征，而 GCN 会同时看节点自己的特征和邻居节点的信息。

对于每一层 GCN，可以把核心计算理解为：

```text
H_next = activation(A_norm × H_current × W)
```

其中：

- `H_current` 是当前节点表示。
- `A_norm` 是归一化后的图邻接矩阵。
- `W` 是可训练权重。
- `A_norm × H_current` 表示把邻居节点的信息聚合到当前节点。

本项目里，GCN 的意义是：如果个人博客之间更倾向互相链接，非博客站点也有不同的连接模式，那么图邻域信息可以帮助模型修正只看 URL/title 时的判断。

## 4. 当前模型架构

实现位置：

- `trainer/graph/dataset.py`
- `trainer/graph/gcn.py`
- `trainer/graph/pipeline.py`

当前模型已从第一版两层 GCN 升级为 residual multi-hop GCN：

```text
TF-IDF URL/title/metadata features
  + structured URL/title/page-signals
  + graph degree metadata
  -> Linear(input_dim, hidden_dim)
  -> repeated residual graph blocks:
       normalized graph aggregation
       Linear(hidden_dim, hidden_dim)
       ReLU
       Dropout
       residual add + LayerNorm
  -> Linear(hidden_dim, 2)
  -> softmax blog probability
```

默认超参数：

- `max_features = 4096`
- `hidden_dim = 64`
- `layers = 3`
- `epochs = 200`
- `learning_rate = 0.01`
- `weight_decay = 5e-4`
- `dropout = 0.35`
- `patience = 25`
- `seed = 7`

本次 smoke run 为了快速验证，使用了：

```bash
.venv/bin/python -m trainer.cli train-gcn \
  --dataset-dir data/dataset \
  --epochs 30 \
  --patience 8 \
  --max-features 2048 \
  --hidden-dim 64
```

## 5. 节点特征

当前图模型使用三类节点特征：

- URL/title/metadata 字符级 TF-IDF
- 复用 trainer 的结构化 URL、title、页面语义特征
- graph degree / in-degree / out-degree / reciprocity proxy / icon / status metadata

```text
url <normalized_url> domain <domain> title <title> identity <identity_reason_codes> status <crawl_status>
```

然后用 `TfidfVectorizer` 做字符 n-gram：

- analyzer: `char_wb`
- ngram_range: `(3, 5)`
- max_features: CLI 控制

结构化部分会补充：

- URL path/query/domain 形态
- title 关键词
- RSS、归档、标签、友链、评论、公司/产品/招聘等 page semantic signals
- 图度数和已持久化连接数

## 6. 图构建

训练主键是 `normalized_url`，不是 graph id。

graph id 只用于当前 snapshot 内部索引。标签和节点通过 `crawler.crawling.normalization.normalize_url` 对齐。

边处理：

- 原始 friend-link 边是有向边。
- 当前 GCN 训练时会转为无向图。
- 每个节点会加入 self-loop。
- 邻接矩阵使用对称归一化：

```text
A_norm = D^(-1/2) × (A + I) × D^(-1/2)
```

这样可以避免高连接度节点在聚合时数值过大。

## 7. 训练与切分

只有 graph-in labeled nodes 会参与监督训练和评估。未标注节点仍保留在图里参与 message passing。

当前切分方式：

- train: `70%`
- val: `15%`
- test: `15%`

切分只发生在已标注且能对齐到 graph 的节点上，并使用 stratified split 保持 `blog / non_blog` 比例。

本次真实运行切分：

```json
{
  "train": {"non_blog": 216, "blog": 335},
  "val": {"non_blog": 46, "blog": 72},
  "test": {"non_blog": 47, "blog": 72}
}
```

训练损失：

```text
CrossEntropyLoss(logits[train_nodes], labels[train_nodes])
```

早停标准：

- 监控 validation F1。
- 保留 validation F1 最好的模型参数。

## 8. 评估指标

当前输出：

- accuracy
- precision
- recall
- F1
- PR-AUC
- ROC-AUC
- TP / FP / TN / FN

评估文件：

- `metrics.json`
- `predictions_labeled.csv`
- `report.md`

注意：这些指标是 graph-in 指标，不代表对所有 URL 的冷启动分类能力。对于没有进入 graph 的 URL，仍然需要 URL/title baseline 或其他冷启动模型。

## 9. 当前结果

当前真实运行输出目录：

```text
data/model/gcn/2605051437
```

测试集指标：

```json
{
  "accuracy": 0.831933,
  "precision": 0.833333,
  "recall": 0.902778,
  "f1": 0.866667,
  "pr_auc": 0.935235,
  "roc_auc": 0.90721,
  "tp": 65,
  "fp": 13,
  "tn": 34,
  "fn": 7
}
```

这说明第一版 GCN 已经可以学到有用信号。不过这还不能证明 GCN 稳定优于现有 baseline，因为当前只跑了一个 seed，也还没有同 split 下的 `tfidf_lr` 对照。

### Residual GCN 更新结果

更新后的 residual GCN 运行命令：

```bash
.venv/bin/python -m trainer.cli train-gcn \
  --dataset-dir data/dataset \
  --epochs 40 \
  --patience 10 \
  --max-features 2048 \
  --hidden-dim 64 \
  --layers 3
```

输出目录：

```text
data/model/gcn/2605231511
```

测试集指标：

```json
{
  "accuracy": 0.714286,
  "precision": 0.702128,
  "recall": 0.916667,
  "f1": 0.795181,
  "pr_auc": 0.882051,
  "roc_auc": 0.825946,
  "threshold": 0.574603,
  "tp": 66,
  "fp": 28,
  "tn": 19,
  "fn": 6
}
```

这次结果是一个重要的负向发现：更复杂的 residual GCN 和更多结构化图特征并没有自动超过第一版两层 GCN，也没有超过增强后的 `tfidf_svm`。当前最可能的问题是 graph-in split 太小、非博客节点图结构分布偏窄、全图 transductive message passing 容易把多数 blog 邻域信号扩散到非博客点。下一步应做边消融、community holdout、同 split 文本 baseline、GraphSAGE/GAT 或 stacking，而不是直接发布这个 residual GCN。

### Graph Edge Ablation

为了判断 friend-link 边是否真的提供增益，新增了：

- `--graph-mode full`：使用完整图边。
- `--graph-mode self_loop`：只保留 self-loop，相当于同样网络结构但不做邻居 message passing。
- `--graph-mode dropout --edge-dropout 0.5`：确定性丢弃 50% 图边，检查边噪声影响。

同一配置下的测试集对比：

| Mode | Run | Edges Used | Precision | Recall | F1 | PR-AUC | Accuracy |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `full` | `data/model/gcn/2605231511` | `46836` | `0.702128` | `0.916667` | `0.795181` | `0.882051` | `0.714286` |
| `self_loop` | `data/model/gcn/2605231518` | `0` | `0.683168` | `0.958333` | `0.797688` | `0.878203` | `0.705882` |
| `dropout 0.5` | `data/model/gcn/2605231519` | `23496` | `0.835821` | `0.777778` | `0.805755` | `0.872559` | `0.773109` |

结论：完整图边没有明显正增益；50% edge dropout 稍微改善 F1 和 precision，但 PR-AUC 没有超过 full graph。这说明 friend-link 图存在信号，但边噪声较大，单纯全图 message passing 会把 blog-majority 邻域信号扩散到非博客节点。下一轮应优先做边质量建模、社区 holdout 和 stacking，而不是继续加深 GCN。

## 10. 已知限制

- 当前只做单 seed，不足以判断稳定性。
- 当前 split 是 stratified random split，不是 domain/community holdout。
- 当前没有和 `tfidf_lr`、`structured_lr` 做同 split 对照。
- 当前只用 URL/title TF-IDF，没有正文、社区发现、node2vec 或 graph stats 特征。
- 当前 graph message passing 使用全图结构，因此这是 graph-in / transductive 风格评估。

## 11. 后续建议

下一步优先做：

1. 多 seed 运行，报告均值和标准差。
2. 同一 graph-in split 下跑 `tfidf_lr` baseline。
3. 增加 graph stats / community baseline。
4. 增加 domain holdout 或 community holdout。
5. 对比有图边和去图边的消融。
6. 再决定是否引入 GraphSAGE、GAT 或 PyTorch Geometric。

## 12. 使用命令

默认训练：

```bash
.venv/bin/python -m trainer.cli train-gcn --dataset-dir data/dataset
```

快速 smoke run：

```bash
.venv/bin/python -m trainer.cli train-gcn \
  --dataset-dir data/dataset \
  --epochs 30 \
  --patience 8 \
  --max-features 2048 \
  --hidden-dim 64
```

测试：

```bash
.venv/bin/python -m pytest trainer/tests/test_graph_gcn.py trainer/tests/test_cli_entrypoint.py
```
