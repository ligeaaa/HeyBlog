from __future__ import annotations

import csv
from pathlib import Path

from agent.config import AgentSettings
from agent.config import ProviderConfig
from agent.schema import PageFetchOutcome
from data_preprocessing.build_agent_text_dataset import build_text_augmented_dataset


class StubPageFetcher:
    def __init__(self, outcomes: dict[str, PageFetchOutcome]) -> None:
        self.outcomes = outcomes
        self.calls: list[list[str]] = []

    def fetch_many(self, urls: list[str]) -> dict[str, PageFetchOutcome]:
        self.calls.append(list(urls))
        return {url: self.outcomes[url] for url in urls}


def _settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings(
        default_provider="deepseek",
        default_model="deepseek-chat",
        provider_configs={
            "deepseek": ProviderConfig(
                name="deepseek",
                model="deepseek-chat",
                api_key="dummy",
                base_url="https://api.deepseek.com",
            )
        },
        output_root=tmp_path / "agent-evals",
    )


def test_build_text_augmented_dataset_writes_text_column(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(
        "url,title,label\n"
        "https://blog.example.com,My Blog,blog\n"
        "https://tool.example.com,Tool,others\n",
        encoding="utf-8",
    )
    output_csv = tmp_path / "with-text.csv"
    fetcher = StubPageFetcher(
        {
            "https://blog.example.com": PageFetchOutcome(
                request_url="https://blog.example.com",
                final_url="https://blog.example.com/home",
                page_text="hello world",
                fetch_status="success",
                error_kind=None,
                used_page_content=True,
            ),
            "https://tool.example.com": PageFetchOutcome(
                request_url="https://tool.example.com",
                final_url=None,
                page_text=None,
                fetch_status="failed",
                error_kind="timeout",
                used_page_content=False,
            ),
        }
    )

    result = build_text_augmented_dataset(
        csv_path=source_csv,
        output_csv=output_csv,
        fetch_batch_size=1,
        settings=_settings(tmp_path),
        fetcher=fetcher,
    )

    with output_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert fetcher.calls == [["https://blog.example.com"], ["https://tool.example.com"]]
    assert rows == [
        {
            "url": "https://blog.example.com",
            "title": "My Blog",
            "label": "blog",
            "text": "hello world",
        },
        {
            "url": "https://tool.example.com",
            "title": "Tool",
            "label": "others",
            "text": "",
        },
    ]
    assert result["output_csv"] == str(output_csv)
    assert result["total_rows"] == 2
    assert result["rows_with_text"] == 1
    assert result["text_coverage"] == 0.5


def test_build_text_augmented_dataset_serializes_multiline_text_as_single_line(tmp_path: Path) -> None:
    source_csv = tmp_path / "source.csv"
    source_csv.write_text(
        "url,title,label\n"
        "https://blog.example.com,My Blog,blog\n",
        encoding="utf-8",
    )
    output_csv = tmp_path / "with-text.csv"
    fetcher = StubPageFetcher(
        {
            "https://blog.example.com": PageFetchOutcome(
                request_url="https://blog.example.com",
                final_url="https://blog.example.com/home",
                page_text="line 1\nline 2\nline 3",
                fetch_status="success",
                error_kind=None,
                used_page_content=True,
            )
        }
    )

    build_text_augmented_dataset(
        csv_path=source_csv,
        output_csv=output_csv,
        settings=_settings(tmp_path),
        fetcher=fetcher,
    )

    raw_csv = output_csv.read_text(encoding="utf-8")
    assert "line 1\\nline 2\\nline 3" in raw_csv
    assert "line 1\nline 2\nline 3" not in raw_csv

    with output_csv.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows[0]["text"] == "line 1\\nline 2\\nline 3"
