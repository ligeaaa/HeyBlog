"""TF-IDF linear SVM baseline over URL and title inputs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.sparse import hstack
from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.svm import SVC

from trainer.config import ModelConfig
from trainer.dataset.schema import SupervisedSample
from trainer.features.assemble import build_tfidf_documents
from trainer.models.sklearn_utils import build_linear_svm
from trainer.models.sklearn_utils import identity_analyzer
from trainer.models.sklearn_utils import positive_class_probabilities
from trainer.models.sklearn_utils import summarize_linear_weights


@dataclass(slots=True)
class TfidfSVMBaseline:
    model_name: str
    threshold: float
    url_vectorizer: TfidfVectorizer
    title_vectorizer: TfidfVectorizer
    estimator: SVC
    metadata: dict[str, Any]

    def _transform(self, samples: list[SupervisedSample]) -> spmatrix:
        url_docs, title_docs = build_tfidf_documents(
            samples,
            url_char_ngram_range=tuple(self.metadata["url_char_ngram_range"]),
            title_word_ngram_range=tuple(self.metadata["title_word_ngram_range"]),
        )
        url_features = self.url_vectorizer.transform(url_docs)
        title_features = self.title_vectorizer.transform(title_docs)
        return hstack([url_features, title_features], format="csr")

    def predict_proba(self, samples: list[SupervisedSample]) -> list[float]:
        return positive_class_probabilities(self.estimator, self._transform(samples))

    def feature_summary(self) -> dict[str, Any]:
        feature_names = np.concatenate(
            [
                np.asarray([f"url_tfidf:{name}" for name in self.url_vectorizer.get_feature_names_out()], dtype=object),
                np.asarray([f"title_tfidf:{name}" for name in self.title_vectorizer.get_feature_names_out()], dtype=object),
            ]
        )
        return summarize_linear_weights(self.estimator, feature_names)

    def training_log(self) -> str:
        feature_count = len(self.url_vectorizer.get_feature_names_out()) + len(self.title_vectorizer.get_feature_names_out())
        classes = ",".join(str(value) for value in self.estimator.classes_.tolist())
        return "\n".join(
            [
                "estimator=tfidf_linear_svm",
                f"support_vectors={self.estimator.n_support_.tolist()}",
                f"feature_count={feature_count}",
                f"classes={classes}",
            ]
        )


def train_tfidf_svm_baseline(
    train_samples: list[SupervisedSample],
    model_config: ModelConfig,
) -> TfidfSVMBaseline:
    url_docs, title_docs = build_tfidf_documents(
        train_samples,
        url_char_ngram_range=model_config.url_char_ngram_range,
        title_word_ngram_range=model_config.title_word_ngram_range,
    )
    url_vectorizer = TfidfVectorizer(
        analyzer=identity_analyzer,
        lowercase=False,
        token_pattern=None,
        preprocessor=None,
        tokenizer=None,
        min_df=model_config.min_df,
    )
    title_vectorizer = TfidfVectorizer(
        analyzer=identity_analyzer,
        lowercase=False,
        token_pattern=None,
        preprocessor=None,
        tokenizer=None,
        min_df=model_config.min_df,
    )
    url_features = url_vectorizer.fit_transform(url_docs)
    title_features = title_vectorizer.fit_transform(title_docs)
    matrix = hstack([url_features, title_features], format="csr")
    labels = [1 if sample.binary_label == "blog" else 0 for sample in train_samples]
    estimator = build_linear_svm(seed=model_config.seed, l2_strength=model_config.l2_strength)
    estimator.fit(matrix, labels)
    return TfidfSVMBaseline(
        model_name="tfidf_svm",
        threshold=model_config.threshold,
        url_vectorizer=url_vectorizer,
        title_vectorizer=title_vectorizer,
        estimator=estimator,
        metadata=model_config.to_dict(),
    )
