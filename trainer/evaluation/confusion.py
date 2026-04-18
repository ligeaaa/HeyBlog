"""Confusion-matrix formatting helpers."""

from __future__ import annotations


def build_confusion_matrix(counts: dict[str, int]) -> dict[str, dict[str, int]]:
    return {
        "gold_blog": {
            "pred_blog": counts["tp"],
            "pred_non_blog": counts["fn"],
        },
        "gold_non_blog": {
            "pred_blog": counts["fp"],
            "pred_non_blog": counts["tn"],
        },
    }
