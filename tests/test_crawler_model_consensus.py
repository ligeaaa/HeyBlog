"""Tests for the crawler model-consensus decision step."""

from __future__ import annotations

import json
from pathlib import Path

from crawler.crawling.decisions.consensus import ModelConsensusDecider
from crawler.crawling.decisions.consensus import ModelConsensusFilter
from crawler.crawling.decisions.base import UrlCandidateContext
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
        self.samples: list[object] = []

    def predict_proba(self, samples: list[object]) -> list[float]:
        """Return the same probability for each requested sample.

        Args:
            samples: Input samples whose content is irrelevant for this stub.

        Returns:
            One probability per sample, all set to the configured value.
        """
        self.samples.extend(samples)
        return [self.probability for _ in samples]


def _write_model_run(
    model_root: Path,
    model_name: str,
    run_name: str,
    *,
    threshold: float = 0.5,
    metrics: dict[str, float] | None = None,
) -> Path:
    """Create a minimal trainer run directory for consensus-decider tests.

    Args:
        model_root: Root directory containing all per-model run directories.
        model_name: Name of the model directory to create.
        run_name: Timestamp-like run directory name.
        threshold: Threshold written into ``config.json`` for fallback reads.
        metrics: Optional evaluation metrics written into ``metrics.json``.

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
    if metrics is not None:
        (run_dir / "metrics.json").write_text(json.dumps(metrics), encoding="utf-8")
    return run_dir


def test_model_consensus_rejects_when_all_models_predict_non_blog(tmp_path: Path, monkeypatch) -> None:
    """Weighted consensus should reject when combined model evidence is non-blog."""
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


def test_model_consensus_keeps_url_when_legacy_any_blog_strategy_has_one_blog_vote(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Legacy any-blog consensus should keep a URL when one model votes blog."""
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

    decision = ModelConsensusDecider(model_root=model_root, strategy="any_blog").decide(
        "https://friend.example.com/",
        "source.example.com",
        link_text="My Blog",
        context_text="友情链接",
    )

    assert decision.accepted is True
    assert decision.reasons == ("model_consensus_kept",)
    assert predictors["tfidf"].samples[0].title == "My Blog"


def test_model_consensus_majority_rejects_when_only_one_of_three_models_votes_blog(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Majority consensus should reject if fewer than half the models vote blog."""
    model_root = tmp_path / "models"
    _write_model_run(model_root, "structured", "2604120847")
    _write_model_run(model_root, "tfidf", "2604120852")
    _write_model_run(model_root, "tfidf_svm", "2604120853")

    predictors = {
        "structured": StubPredictor(0.20),
        "tfidf": StubPredictor(0.30),
        "tfidf_svm": StubPredictor(0.90),
    }
    monkeypatch.setattr(
        "crawler.crawling.decisions.consensus.load_model",
        lambda path: predictors[path.parent.parent.name],
    )

    decision = ModelConsensusDecider(model_root=model_root, strategy="majority_blog").decide(
        "https://friend.example.com/",
        "source.example.com",
    )

    assert decision.accepted is False
    assert decision.reasons == ("model_consensus_all_non_blog",)


def test_model_consensus_weighted_average_prefers_high_metric_model(tmp_path: Path, monkeypatch) -> None:
    """Weighted consensus should let a strong validated model dominate weak old runs."""
    model_root = tmp_path / "models"
    _write_model_run(model_root, "old_structured", "2604120847", metrics={"f1": 0.10})
    _write_model_run(model_root, "tfidf_svm", "2605231457", metrics={"f1": 0.95})

    predictors = {
        "old_structured": StubPredictor(0.10),
        "tfidf_svm": StubPredictor(0.80),
    }
    monkeypatch.setattr(
        "crawler.crawling.decisions.consensus.load_model",
        lambda path: predictors[path.parent.parent.name],
    )

    decision = ModelConsensusDecider(model_root=model_root, strategy="weighted_average").decide(
        "https://friend.example.com/",
        "source.example.com",
        link_text="Blog",
    )

    assert decision.accepted is True
    assert decision.reasons == ("model_consensus_kept",)


def test_model_consensus_weight_falls_back_when_metrics_are_missing(tmp_path: Path, monkeypatch) -> None:
    """Weighted consensus should still work for old runs without metrics.json."""
    model_root = tmp_path / "models"
    _write_model_run(model_root, "old_structured", "2604120847")
    _write_model_run(model_root, "tfidf_svm", "2605231457", metrics={"f1": 0.80})

    predictors = {
        "old_structured": StubPredictor(0.10),
        "tfidf_svm": StubPredictor(0.90),
    }
    monkeypatch.setattr(
        "crawler.crawling.decisions.consensus.load_model",
        lambda path: predictors[path.parent.parent.name],
    )

    decision = ModelConsensusDecider(model_root=model_root, strategy="weighted_average").decide(
        "https://friend.example.com/",
        "source.example.com",
    )

    assert decision.accepted is False
    assert decision.reasons == ("model_consensus_all_non_blog",)


def test_model_consensus_uses_anchor_context_when_link_text_is_missing(tmp_path: Path, monkeypatch) -> None:
    """Consensus samples should preserve crawler anchor context for feature-rich models."""
    model_root = tmp_path / "models"
    _write_model_run(model_root, "hybrid_mlp", "2604120859")

    predictor = StubPredictor(0.70)
    monkeypatch.setattr("crawler.crawling.decisions.consensus.load_model", lambda _path: predictor)

    decision = ModelConsensusDecider(model_root=model_root).decide(
        "https://friend.example.com/",
        "source.example.com",
        context_text="友情链接 RSS 归档 标签",
    )

    assert decision.accepted is True
    assert predictor.samples[0].title == "友情链接 RSS 归档 标签"


def test_model_consensus_skips_cleanly_when_no_models_exist(tmp_path: Path) -> None:
    """Consensus should not block crawler candidates when no model artifacts exist."""
    decision = ModelConsensusDecider(model_root=tmp_path / "missing").decide(
        "https://friend.example.com/",
        "source.example.com",
    )

    assert decision.accepted is True
    assert decision.reasons == ("model_consensus_skipped_no_models",)


def test_model_api_consensus_uses_single_prediction(monkeypatch, tmp_path: Path) -> None:
    """The configured runtime path delegates URL classification to Model API."""
    monkeypatch.setattr(
        "crawler.crawling.decisions.consensus.ModelApiClient.classify_url",
        lambda self, url, title="": {"url": url, "label": "blog", "probability": 0.99},
    )
    decision = ModelConsensusFilter(
        model_root=tmp_path / "unused",
        model_api_base_url="http://model-api:8040",
    ).apply(
        UrlCandidateContext(
            source_blog_id=1,
            source_domain="source.example.com",
            normalized_url="https://friend.example.com/",
            link_text="My blog",
        )
    )
    assert decision.confirmed is True
    assert decision.accepted_by == "model"


def test_pipeline_appends_model_consensus_step_when_enabled(tmp_path: Path) -> None:
    """Pipeline should wire the consensus step after deterministic hard rules."""
    settings = Settings(
        db_path=tmp_path / "db.sqlite",
        seed_path=tmp_path / "seed.csv",
        export_dir=tmp_path / "exports",
        decision_model_root=tmp_path / "models",
        decision_model_consensus_enabled=True,
        decision_model_consensus_strategy="majority_blog",
    )

    pipeline = CrawlPipeline(settings, Repository(settings.db_path))

    assert len(pipeline.orchestrator.decision_chain.steps) >= 2
    assert pipeline.orchestrator.decision_chain.steps[-1].__class__.__name__ == "ModelConsensusFilter"
    assert pipeline.orchestrator.decision_chain.steps[-1].strategy == "majority_blog"
