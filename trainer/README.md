# Trainer

`trainer/` 是 HeyBlog 首轮 `url + title` 博客二分类的离线 workflow package。

## 目标

- 从 `data/blog-label-training-*.csv` 读取人工标注导出
- 冻结首轮二分类映射：`blog -> blog`、`others -> non_blog`、其他标签 -> `excluded`
- 生成 domain-aware 的 `train / val / test`
- 训练两个经典 baseline：
  - `structured`
  - `tfidf`
- 输出 metrics、误判样本、confusion matrix 和 markdown 报告

## 命令

```bash
python -m trainer.cli prepare-dataset
```

```bash
python -m trainer.cli train --dataset-dir data/trainer/datasets/blog-label-training-2026-04-11-baseline-v1 --model structured
```

```bash
python -m trainer.cli evaluate --run-dir data/trainer/runs/<run_id>
```

```bash
python -m trainer.cli full-run --source-csv data/blog-label-training-2026-04-11.csv
```

## 输出

- `data/trainer/datasets/<dataset_version>/`
  - `raw_export.csv`
  - `label_resolution.jsonl`
  - `full_supervised.jsonl`
  - `train.jsonl`
  - `val.jsonl`
  - `test.jsonl`
  - `dataset_stats.json`
  - `split_manifest.json`
- `data/trainer/runs/<run_id>/`
  - `config.json`
  - `metrics.json`
  - `predictions_test.csv`
  - `confusion_matrix.json`
  - `top_errors.csv`
  - `feature_summary.json`
  - `model.joblib`
  - `report.md`

## 说明

- 当前 baseline 全部采用纯 Python 实现，没有引入 `sklearn` / `numpy`
- `model.joblib` 只是沿用常见扩展名，底层实际使用的是标准库 `pickle`
- 若后续要把 `company` 并入 `non_blog`，只需修改 `trainer/labeling/label_mapping.py` 并重新跑 dataset + runs
