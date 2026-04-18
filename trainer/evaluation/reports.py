"""Markdown report generation for trainer runs."""

from __future__ import annotations

from pathlib import Path


def build_run_report(
    *,
    model_name: str,
    dataset_dir: Path,
    metrics: dict[str, object],
    dataset_stats: dict[str, object],
    split_manifest: dict[str, object],
) -> str:
    sample_counts = split_manifest.get("sample_counts", {})
    label_counts = split_manifest.get("label_counts", {})
    return "\n".join(
        [
            f"# Trainer Run Report: {model_name}",
            "",
            f"- Dataset: `{dataset_dir}`",
            f"- Precision: `{metrics['precision']}`",
            f"- Recall: `{metrics['recall']}`",
            f"- F1: `{metrics['f1']}`",
            f"- PR-AUC: `{metrics['pr_auc']}`",
            "",
            "## Dataset",
            "",
            f"- Total records: `{dataset_stats['total_records']}`",
            f"- Supervised records: `{dataset_stats['supervised_records']}`",
            f"- Resolution counts: `{dataset_stats['resolution_counts']}`",
            f"- Binary label counts: `{dataset_stats['binary_label_counts']}`",
            "",
            "## Split Summary",
            "",
            f"- Sample counts: `{sample_counts}`",
            f"- Label counts: `{label_counts}`",
            "",
            "## Notes",
            "",
            "- `blog` maps to `blog`; `others` and `company` map to `non_blog` in the current baseline dataset.",
            "- Domain-aware split keeps the same domain out of multiple splits.",
        ]
    ) + "\n"


def build_full_run_summary(results: list[dict[str, object]]) -> str:
    lines = [
        "# Full Trainer Run Summary",
        "",
        "| Model | Precision | Recall | F1 | PR-AUC | Run Dir |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for result in results:
        metrics = result["metrics"]
        lines.append(
            "| {model} | {precision} | {recall} | {f1} | {pr_auc} | `{run_dir}` |".format(
                model=result["model_name"],
                precision=metrics["precision"],
                recall=metrics["recall"],
                f1=metrics["f1"],
                pr_auc=metrics["pr_auc"],
                run_dir=result["run_dir"],
            )
        )
    lines.append("")
    return "\n".join(lines)
