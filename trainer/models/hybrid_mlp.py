"""Hybrid MLP over URL, title, and page-signal features."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import hstack
from scipy.sparse import spmatrix
from sklearn.feature_extraction import DictVectorizer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.neural_network import MLPClassifier

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_structured_feature_rows
from trainer.features.assemble import build_tfidf_documents
from trainer.models.sklearn_utils import build_mlp_classifier
from trainer.models.sklearn_utils import build_training_log
from trainer.models.sklearn_utils import identity_analyzer
from trainer.models.sklearn_utils import positive_class_probabilities
from trainer.models.sklearn_utils import summarize_weight_vector


@dataclass(slots=True)
class HybridMlpBaseline:
    """Persist the vectorizers and MLP estimator for fused inference.

    Attributes:
        model_name: Registered trainer model name.
        threshold: Probability threshold used to emit the blog class.
        structured_vectorizer: Vectorizer for handcrafted URL/title/page features.
        url_vectorizer: TF-IDF vectorizer for URL tokens and n-grams.
        title_vectorizer: TF-IDF vectorizer for title plus page-signal tokens.
        estimator: Trained sklearn MLP classifier.
        metadata: Serialized model configuration.
    """

    model_name: str
    threshold: float
    structured_vectorizer: DictVectorizer
    url_vectorizer: TfidfVectorizer
    title_vectorizer: TfidfVectorizer
    estimator: MLPClassifier
    metadata: dict[str, Any]

    def _transform(self, samples: list[SupervisedSample]) -> spmatrix:
        """Vectorize samples into the fused feature matrix used by the MLP.

        Args:
            samples: Supervised or crawler-inference samples.

        Returns:
            CSR sparse matrix combining structured, URL TF-IDF, and title/page
            TF-IDF features.
        """

        structured_rows = build_structured_feature_rows(samples)
        url_docs, title_docs = build_tfidf_documents(
            samples,
            url_char_ngram_range=tuple(self.metadata["url_char_ngram_range"]),
            title_word_ngram_range=tuple(self.metadata["title_word_ngram_range"]),
            title_token_chunk_size=self.metadata["title_token_chunk_size"],
        )
        return hstack(
            [
                self.structured_vectorizer.transform(structured_rows),
                self.url_vectorizer.transform(url_docs),
                self.title_vectorizer.transform(title_docs),
            ],
            format="csr",
        )

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        """Return blog-class probabilities for the provided samples."""

        return positive_class_probabilities(self.estimator, self._transform(samples))

    def feature_summary(self) -> dict[str, Any]:
        """Return a stable proxy feature summary for the first MLP layer."""

        feature_names = np.concatenate(
            [
                np.asarray(
                    [f"structured:{name}" for name in self.structured_vectorizer.get_feature_names_out()],
                    dtype=object,
                ),
                np.asarray([f"url_tfidf:{name}" for name in self.url_vectorizer.get_feature_names_out()], dtype=object),
                np.asarray(
                    [f"title_page_tfidf:{name}" for name in self.title_vectorizer.get_feature_names_out()],
                    dtype=object,
                ),
            ]
        )
        first_layer = np.asarray(self.estimator.coefs_[0], dtype=float)
        proxy_weights = np.linalg.norm(first_layer, axis=1)
        return {
            "first_layer_proxy": summarize_weight_vector(proxy_weights, feature_names),
            "hidden_layer_sizes": list(self.estimator.hidden_layer_sizes),
        }

    def training_log(self) -> str:
        """Return a compact training log for artifact inspection."""

        feature_count = (
            len(self.structured_vectorizer.get_feature_names_out())
            + len(self.url_vectorizer.get_feature_names_out())
            + len(self.title_vectorizer.get_feature_names_out())
        )
        return build_training_log(self.estimator, feature_count=feature_count)


def _build_token_vectorizer(model_config: ModelConfig) -> TfidfVectorizer:
    """Create the shared pre-tokenized vectorizer used by hybrid text lanes."""

    return TfidfVectorizer(
        analyzer=identity_analyzer,
        lowercase=False,
        token_pattern=None,
        preprocessor=None,
        tokenizer=None,
        min_df=model_config.min_df,
        sublinear_tf=True,
    )


def train_hybrid_mlp_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> HybridMlpBaseline:
    """Train the fused URL/title/page feature MLP baseline.

    Args:
        train_samples: Domain-split training samples.
        model_config: Trainer model configuration.

    Returns:
        Trained hybrid MLP baseline object with vectorizers and estimator.
    """

    structured_rows = build_structured_feature_rows(train_samples)
    url_docs, title_docs = build_tfidf_documents(
        train_samples,
        url_char_ngram_range=model_config.url_char_ngram_range,
        title_word_ngram_range=model_config.title_word_ngram_range,
        title_token_chunk_size=model_config.title_token_chunk_size,
    )
    structured_vectorizer = DictVectorizer(sparse=True)
    url_vectorizer = _build_token_vectorizer(model_config)
    title_vectorizer = _build_token_vectorizer(model_config)
    matrix = hstack(
        [
            structured_vectorizer.fit_transform(structured_rows),
            url_vectorizer.fit_transform(url_docs),
            title_vectorizer.fit_transform(title_docs),
        ],
        format="csr",
    )
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    estimator = build_mlp_classifier(seed=model_config.seed, epochs=model_config.epochs, sample_count=len(train_samples))
    estimator.fit(matrix, labels)
    return HybridMlpBaseline(
        model_name=model_config.model_name,
        threshold=model_config.threshold,
        structured_vectorizer=structured_vectorizer,
        url_vectorizer=url_vectorizer,
        title_vectorizer=title_vectorizer,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
