"""Build a text-augmented CSV for agent evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from agent.config import AgentSettings
from data_preprocessing.fetching import PageFetcher
from trainer.constants import DEFAULT_DATA_ROOT
from trainer.io.artifact_writer import write_csv
from trainer.io.dataset_export import load_raw_label_rows
from tqdm import tqdm


def build_text_augmented_dataset(
    *,
    csv_path: Path,
    output_csv: Path | None = None,
    fetch_batch_size: int = 32,
    settings: AgentSettings | None = None,
    fetcher: PageFetcher | None = None,
) -> dict[str, Any]:
    """Fetch page text for each CSV row and write an augmented dataset.

    Args:
        csv_path: Source CSV containing ``url``, ``title``, and ``label``.
        output_csv: Optional explicit output path. When omitted, writes a file
            next to the input CSV using the ``-with-text`` suffix.
        fetch_batch_size: Number of URLs fetched per preprocessing batch.
        settings: Optional agent settings. Loaded from env when omitted.
        fetcher: Optional injected page fetcher for tests.

    Returns:
        A JSON-serializable summary describing the output dataset path and basic
        coverage counts.
    """
    resolved_settings = settings or AgentSettings.from_env()
    rows = load_raw_label_rows(csv_path)
    unique_urls = list(dict.fromkeys(row.url for row in rows))
    resolved_fetcher = fetcher or PageFetcher(resolved_settings)
    resolved_batch_size = max(1, fetch_batch_size)
    fetch_outcomes: dict[str, Any] = {}
    with tqdm(total=len(unique_urls), desc="Fetching text", unit="url") as progress:
        for start in range(0, len(unique_urls), resolved_batch_size):
            batch = unique_urls[start : start + resolved_batch_size]
            fetch_outcomes.update(resolved_fetcher.fetch_many(batch))
            progress.update(len(batch))

    output_rows: list[dict[str, str]] = []
    rows_with_text = 0
    for row in rows:
        fetch = fetch_outcomes[row.url]
        text = fetch.page_text if fetch.used_page_content and fetch.page_text is not None else ""
        if text:
            rows_with_text += 1
        output_rows.append(
            {
                "url": row.url,
                "title": row.title,
                "label": row.label,
                "text": _serialize_text_field(text),
            }
        )

    resolved_output = output_csv or csv_path.with_name(f"{csv_path.stem}-with-text.csv")
    write_csv(
        resolved_output,
        fieldnames=["url", "title", "label", "text"],
        rows=output_rows,
    )
    return {
        "output_csv": str(resolved_output),
        "total_rows": len(rows),
        "rows_with_text": rows_with_text,
        "text_coverage": round(_safe_divide(rows_with_text, len(rows)), 6),
    }


def _safe_divide(numerator: float, denominator: float) -> float:
    """Safely divide values when computing coverage."""
    if denominator == 0:
        return 0.0
    return numerator / denominator


def _serialize_text_field(text: str) -> str:
    """Serialize fetched page text into a single-line CSV-safe payload.

    Args:
        text: Raw fetched page text that may contain real newlines.

    Returns:
        A single-line string where newline characters are stored as literal
        ``\\n`` sequences so the dataset remains easy to inspect in editors.
    """
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    return json.dumps(normalized, ensure_ascii=False)[1:-1]


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for the text-dataset preprocessing script."""
    default_csv = DEFAULT_DATA_ROOT / "blog-label-training-2026-04-11.csv"
    parser = argparse.ArgumentParser(description="Build a text-augmented dataset for agent eval.")
    parser.add_argument(
        "--csv",
        type=Path,
        default=default_csv,
        help=f"Path to the source CSV. Defaults to {default_csv}.",
    )
    parser.add_argument(
        "--output-csv",
        type=Path,
        default=None,
        help="Optional explicit output CSV path. Defaults to '<input>-with-text.csv'.",
    )
    parser.add_argument(
        "--fetch-batch-size",
        type=int,
        default=32,
        help="Number of URLs fetched per preprocessing batch. Defaults to 32.",
    )
    return parser


def main() -> None:
    """Run the CLI entrypoint for text-dataset preprocessing."""
    args = _build_arg_parser().parse_args()
    result = build_text_augmented_dataset(
        csv_path=args.csv,
        output_csv=args.output_csv,
        fetch_batch_size=args.fetch_batch_size,
    )
    print(result["output_csv"])


if __name__ == "__main__":
    main()
