"""Legacy TF-IDF Naive Bayes model class for runtime unpickling."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scipy.sparse import hstack
from scipy.sparse import spmatrix
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import ComplementNB

from trainer.models.features import build_tfidf_documents
from trainer.models.sklearn_utils import positive_class_probabilities


@dataclass(slots=True)
class TfidfNaiveBayesBaseline:
    """TF-IDF ComplementNB baseline compatible with legacy artifacts."""

    model_name: str
    threshold: float
    url_vectorizer: TfidfVectorizer
    title_vectorizer: TfidfVectorizer
    estimator: ComplementNB
    metadata: dict[str, Any]

    def _transform(self, samples: list[object]) -> spmatrix:
        """Transform runtime samples into the legacy TF-IDF feature matrix."""
        url_docs, title_docs = build_tfidf_documents(
            samples,
            url_char_ngram_range=tuple(self.metadata["url_char_ngram_range"]),
            title_word_ngram_range=tuple(self.metadata["title_word_ngram_range"]),
            title_token_chunk_size=self.metadata["title_token_chunk_size"],
        )
        return hstack(
            [self.url_vectorizer.transform(url_docs), self.title_vectorizer.transform(title_docs)],
            format="csr",
        )

    def predict_proba(self, samples: list[object]) -> list[float]:
        """Return blog probabilities for runtime samples."""
        return positive_class_probabilities(self.estimator, self._transform(samples))

