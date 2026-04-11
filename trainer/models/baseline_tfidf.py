"""TF-IDF baseline over URL and title inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_tfidf_documents
from trainer.features.assemble import merge_feature_maps
from trainer.features.text_vectorizers import TfidfVectorizer
from trainer.models.simple_logistic import SparseLogisticRegression


@dataclass(slots=True)
class TfidfBaseline:
    model_name: str
    threshold: float
    url_vectorizer: TfidfVectorizer
    title_vectorizer: TfidfVectorizer
    estimator: SparseLogisticRegression
    metadata: dict[str, Any]

    def _transform(self, samples: list[SupervisedSample]) -> list[dict[str, float]]:
        url_docs, title_docs = build_tfidf_documents(
            samples,
            url_char_ngram_range=tuple(self.metadata["url_char_ngram_range"]),
            title_word_ngram_range=tuple(self.metadata["title_word_ngram_range"]),
        )
        url_features = self.url_vectorizer.transform(url_docs)
        title_features = self.title_vectorizer.transform(title_docs)
        return [merge_feature_maps(url_map, title_map) for url_map, title_map in zip(url_features, title_features, strict=True)]

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        return self.estimator.predict_proba(self._transform(samples))

    def feature_summary(self) -> dict[str, Any]:
        return self.estimator.top_weight_summary()


def train_tfidf_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> TfidfBaseline:
    url_docs, title_docs = build_tfidf_documents(
        train_samples,
        url_char_ngram_range=model_config.url_char_ngram_range,
        title_word_ngram_range=model_config.title_word_ngram_range,
    )
    url_vectorizer = TfidfVectorizer(prefix="url_tfidf", min_df=model_config.min_df)
    title_vectorizer = TfidfVectorizer(prefix="title_tfidf", min_df=model_config.min_df)
    url_features = url_vectorizer.fit_transform(url_docs)
    title_features = title_vectorizer.fit_transform(title_docs)
    rows = [merge_feature_maps(url_map, title_map) for url_map, title_map in zip(url_features, title_features, strict=True)]
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    estimator = SparseLogisticRegression(
        learning_rate=model_config.learning_rate,
        l2_strength=model_config.l2_strength,
        epochs=model_config.epochs,
        seed=model_config.seed,
    ).fit(rows, labels)
    return TfidfBaseline(
        model_name="tfidf",
        threshold=model_config.threshold,
        url_vectorizer=url_vectorizer,
        title_vectorizer=title_vectorizer,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
