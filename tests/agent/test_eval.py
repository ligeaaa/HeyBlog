from __future__ import annotations

import json
from pathlib import Path

from agent.config import AgentSettings
from agent.config import ProviderConfig
from agent.eval import run_eval
from agent.schema import BlogJudgeResult


class StubClassifier:
    def __init__(self, results: list[BlogJudgeResult]) -> None:
        self.results = results

    async def classify_many(self, inputs, *, progress_callback=None):
        if progress_callback is not None:
            for _ in inputs:
                progress_callback()
        return self.results


def _settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings(
        default_provider="openai",
        default_model="gpt-4o-mini",
        provider_configs={
            "openai": ProviderConfig(name="openai", model="gpt-4o-mini", api_key="key")
        },
        output_root=tmp_path / "agent-evals",
    )


def test_run_eval_writes_summary_and_manifest(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_text(
        "url,title,label,text\n"
        "https://blog.example.com,My Blog,blog,personal notes\n"
        "https://corp.example.com,Docs,others,company docs\n"
        "https://miss.example.com,Missed Blog,blog,blog text\n",
        encoding="utf-8",
    )
    classifier = StubClassifier(
        [
            BlogJudgeResult(
                pred_label="non_blog",
                reason="mistakenly treated as docs",
                provider="openai",
                model="gpt-4o-mini",
                llm_status="success",
            ),
            BlogJudgeResult(
                pred_label="blog",
                reason="mistakenly treated as personal site",
                provider="openai",
                model="gpt-4o-mini",
                llm_status="success",
            ),
            BlogJudgeResult(
                pred_label=None,
                reason="classification_failed: timeout",
                provider="openai",
                model="gpt-4o-mini",
                llm_status="failed",
            ),
        ]
    )
    output_dir = tmp_path / "artifacts"

    result = run_eval(
        csv_path=csv_path,
        settings=_settings(tmp_path),
        output_dir=output_dir,
        classifier=classifier,
    )

    summary = json.loads((output_dir / "summary.json").read_text(encoding="utf-8"))
    manifest_lines = (output_dir / "manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
    false_positive_lines = (output_dir / "false_positives.jsonl").read_text(encoding="utf-8").strip().splitlines()
    false_negative_lines = (output_dir / "false_negatives.jsonl").read_text(encoding="utf-8").strip().splitlines()

    assert result["output_dir"] == str(output_dir)
    assert summary["tp"] == 0
    assert summary["tn"] == 0
    assert summary["fp"] == 1
    assert summary["fn"] == 1
    assert summary["classification_coverage"] == 0.666667
    assert summary["page_fetch_coverage"] == 1.0
    assert summary["eval_seconds"] >= 0
    assert len(manifest_lines) == 3
    assert json.loads(manifest_lines[2])["pred_label"] is None
    assert len(false_positive_lines) == 1
    assert len(false_negative_lines) == 1
    assert json.loads(false_positive_lines[0]) == {
        "gold_label": "non_blog",
        "pred_label": "blog",
        "title": "Docs",
        "url": "https://corp.example.com",
    }
    assert json.loads(false_negative_lines[0]) == {
        "gold_label": "blog",
        "pred_label": "non_blog",
        "title": "My Blog",
        "url": "https://blog.example.com",
    }
    assert result["false_positives"] == [json.loads(false_positive_lines[0])]
    assert result["false_negatives"] == [json.loads(false_negative_lines[0])]


def test_run_eval_requires_text_column(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset-without-text.csv"
    csv_path.write_text(
        "url,title,label\n"
        "https://blog.example.com,My Blog,blog\n",
        encoding="utf-8",
    )

    try:
        run_eval(
            csv_path=csv_path,
            settings=_settings(tmp_path),
            classifier=StubClassifier([]),
        )
    except ValueError as exc:
        assert "missing required 'text' column" in str(exc)
        assert "build_agent_text_dataset" in str(exc)
    else:  # pragma: no cover - the test must fail if no exception is raised.
        raise AssertionError("run_eval() should reject datasets without a text column")


def test_run_eval_restores_serialized_newlines_before_classification(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_text(
        "url,title,label,text\n"
        "https://blog.example.com,My Blog,blog,line 1\\nline 2\n",
        encoding="utf-8",
    )

    class AssertingClassifier:
        async def classify_many(self, inputs, *, progress_callback=None):
            assert inputs[0].page_text == "line 1\nline 2"
            if progress_callback is not None:
                progress_callback()
            return [
                BlogJudgeResult(
                    pred_label="blog",
                    reason="looks like a blog",
                    provider="openai",
                    model="gpt-4o-mini",
                    llm_status="success",
                )
            ]

    result = run_eval(
        csv_path=csv_path,
        settings=_settings(tmp_path),
        output_dir=tmp_path / "artifacts",
        classifier=AssertingClassifier(),
    )

    assert result["summary"]["tp"] == 1


def test_run_eval_truncates_text_before_classification(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_text(
        "url,title,label,text\n"
        "https://blog.example.com,My Blog,blog,abcdefghij\n",
        encoding="utf-8",
    )

    class AssertingClassifier:
        async def classify_many(self, inputs, *, progress_callback=None):
            assert inputs[0].page_text == "abcd"
            if progress_callback is not None:
                progress_callback()
            return [
                BlogJudgeResult(
                    pred_label="blog",
                    reason="looks like a blog",
                    provider="openai",
                    model="gpt-4o-mini",
                    llm_status="success",
                )
            ]

    result = run_eval(
        csv_path=csv_path,
        settings=_settings(tmp_path),
        output_dir=tmp_path / "artifacts",
        classifier=AssertingClassifier(),
        max_text_chars=4,
    )

    assert result["summary"]["tp"] == 1


def test_run_eval_supports_large_text_fields(tmp_path: Path) -> None:
    large_text = "x" * 150000
    csv_path = tmp_path / "dataset.csv"
    csv_path.write_text(
        f"url,title,label,text\nhttps://blog.example.com,My Blog,blog,{large_text}\n",
        encoding="utf-8",
    )

    class AssertingClassifier:
        async def classify_many(self, inputs, *, progress_callback=None):
            assert inputs[0].page_text == large_text[:32]
            if progress_callback is not None:
                progress_callback()
            return [
                BlogJudgeResult(
                    pred_label="blog",
                    reason="looks like a blog",
                    provider="openai",
                    model="gpt-4o-mini",
                    llm_status="success",
                )
            ]

    result = run_eval(
        csv_path=csv_path,
        settings=_settings(tmp_path),
        output_dir=tmp_path / "artifacts",
        classifier=AssertingClassifier(),
        max_text_chars=32,
    )

    assert result["summary"]["tp"] == 1
