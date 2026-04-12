"""Tests for the crawler model-consensus decision step."""

from __future__ import annotations

import json
from pathlib import Path

from crawler.crawling.decisions.consensus import ModelConsensusDecider
from crawler.crawling.pipeline import CrawlPipeline
from persistence_api.repository import Repository
from shared.config import Settings


class StubPredictor:
    """Return a fixed probability for every synthetic crawler sample."""

    def __init__(self, probability: float, *, threshold: float = 0.5) -> None:
        """Store the fixed probability emitted by this stub model.

        Args:
            probability: Probability returned for every sample.
            threshold: Threshold exposed on the stub model for blog voting.

        Returns:
            ``None``. The stub stores deterministic inference parameters.
        """
        self.probability = probability
        self.threshold = threshold

    def predict_proba(self, samples: list[object]) -> list[float]:
        """Return the same probability for each requested sample.

        Args:
            samples: Input samples whose content is irrelevant for this stub.

        Returns:
            One probability per sample, all set to the configured value.
        """
        return [self.probability for _ in samples]


def _write_model_run(model_root: Path, model_name: str, run_name: str, *, threshold: float = 0.5) -> Path:
    """Create a minimal trainer run directory for consensus-decider tests.

    Args:
        model_root: Root directory containing all per-model run directories.
        model_name: Name of the model directory to create.
        run_name: Timestamp-like run directory name.
        threshold: Threshold written into ``config.json`` for fallback reads.

    Returns:
        Path to the created run directory.
    """
    run_dir = model_root / model_name / run_name
    run_dir.mkdir(parents=True)
    (run_dir / "model.joblib").write_bytes(b"stub")
    (run_dir / "config.json").write_text(
        json.dumps({"model_config": {"threshold": threshold}}),
        encoding="utf-8",
    )
    return run_dir


def test_model_consensus_rejects_when_all_models_predict_non_blog(tmp_path: Path, monkeypatch) -> None:
    """Consensus should reject a URL only when every model votes non-blog."""
    model_root = tmp_path / "models"
    _write_model_run(model_root, "structured", "2604120847")
    _write_model_run(model_root, "tfidf", "2604120852")

    predictors = {
        "structured": StubPredictor(0.10),
        "tfidf": StubPredictor(0.20),
    }
    monkeypatch.setattr(
        "crawler.crawling.decisions.consensus.load_model",
        lambda path: predictors[path.parent.parent.name],
    )

    decision = ModelConsensusDecider(model_root=model_root).decide(
        "https://news.example.com/about",
        "source.example.com",
        link_text="About",
        context_text="Friends",
    )

    assert decision.accepted is False
    assert decision.reasons == ("model_consensus_all_non_blog",)


def test_model_consensus_keeps_url_when_any_model_predicts_blog(tmp_path: Path, monkeypatch) -> None:
    """Consensus should keep a URL when at least one model votes blog."""
    model_root = tmp_path / "models"
    _write_model_run(model_root, "structured", "2604120847")
    _write_model_run(model_root, "tfidf", "2604120852")

    predictors = {
        "structured": StubPredictor(0.15),
        "tfidf": StubPredictor(0.82),
    }
    monkeypatch.setattr(
        "crawler.crawling.decisions.consensus.load_model",
        lambda path: predictors[path.parent.parent.name],
    )

    decision = ModelConsensusDecider(model_root=model_root).decide(
        "https://friend.example.com/",
        "source.example.com",
        link_text="My Blog",
        context_text="友情链接",
    )

    assert decision.accepted is True
    assert decision.reasons == ("model_consensus_kept",)


def test_model_consensus_skips_cleanly_when_no_models_exist(tmp_path: Path) -> None:
    """Consensus should not block crawler candidates when no model artifacts exist."""
    decision = ModelConsensusDecider(model_root=tmp_path / "missing").decide(
        "https://friend.example.com/",
        "source.example.com",
    )

    assert decision.accepted is True
    assert decision.reasons == ("model_consensus_skipped_no_models",)


def test_pipeline_appends_model_consensus_step_when_enabled(tmp_path: Path) -> None:
    """Pipeline should wire the consensus step after deterministic hard rules."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        decision_model_root=tmp_path / "models",
        decision_model_consensus_enabled=True,
    )

    pipeline = CrawlPipeline(settings, Repository(settings.db_path))

    assert len(pipeline.orchestrator.decision_chain.steps) == 2
    assert pipeline.orchestrator.decision_chain.steps[1].__class__.__name__ == "ModelConsensusDecider"
