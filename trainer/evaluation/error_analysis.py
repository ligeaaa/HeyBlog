"""Generate error slices from prediction rows."""

from __future__ import annotations

from trainer.models.inference import PredictionRow


def build_top_errors(predictions: list[PredictionRow], *, limit: int = 50) -> list[dict[str, object]]:
    mistakes = [row for row in predictions if row.gold_label != row.pred_label]
    mistakes.sort(key=lambda row: max(row.prob_blog, 1 - row.prob_blog), reverse=True)
    rows: list[dict[str, object]] = []
    for row in mistakes[:limit]:
        error_type = "false_positive" if row.pred_label == "blog" else "false_negative"
        rows.append(
            {
                **row.to_dict(),
                "error_type": error_type,
                "confidence": round(max(row.prob_blog, 1 - row.prob_blog), 6),
            }
        )
    return rows
