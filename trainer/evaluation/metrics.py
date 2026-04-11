"""Metric helpers for binary trainer runs."""

from __future__ import annotations

from trainer.models.inference import PredictionRow


def compute_confusion_counts(predictions: list[PredictionRow]) -> dict[str, int]:
    tp = fp = tn = fn = 0
    for row in predictions:
        if row.gold_label == "blog" and row.pred_label == "blog":
            tp += 1
        elif row.gold_label != "blog" and row.pred_label == "blog":
            fp += 1
        elif row.gold_label != "blog" and row.pred_label != "blog":
            tn += 1
        else:
            fn += 1
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn}


def _safe_divide(numerator: float, denominator: float) -> float:
    if denominator == 0:
        return 0.0
    return numerator / denominator


def compute_pr_auc(predictions: list[PredictionRow]) -> float:
    ranked = sorted(predictions, key=lambda row: row.prob_blog, reverse=True)
    total_positive = sum(1 for row in ranked if row.gold_label == "blog")
    if total_positive == 0:
        return 0.0
    true_positive = 0
    false_positive = 0
    previous_recall = 0.0
    area = 0.0
    for row in ranked:
        if row.gold_label == "blog":
            true_positive += 1
        else:
            false_positive += 1
        precision = _safe_divide(true_positive, true_positive + false_positive)
        recall = _safe_divide(true_positive, total_positive)
        area += (recall - previous_recall) * precision
        previous_recall = recall
    return area


def compute_metrics(predictions: list[PredictionRow]) -> dict[str, float | int]:
    counts = compute_confusion_counts(predictions)
    precision = _safe_divide(counts["tp"], counts["tp"] + counts["fp"])
    recall = _safe_divide(counts["tp"], counts["tp"] + counts["fn"])
    f1 = _safe_divide(2 * precision * recall, precision + recall)
    accuracy = _safe_divide(counts["tp"] + counts["tn"], len(predictions))
    return {
        **counts,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f1": round(f1, 6),
        "accuracy": round(accuracy, 6),
        "pr_auc": round(compute_pr_auc(predictions), 6),
    }
