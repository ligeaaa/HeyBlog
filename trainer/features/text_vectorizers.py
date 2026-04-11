"""Pure-Python TF-IDF vectorizers."""

from __future__ import annotations

from collections import Counter
from math import log


class TfidfVectorizer:
    """A small, deterministic TF-IDF vectorizer for sparse dict outputs."""

    def __init__(self, *, prefix: str, min_df: int = 1) -> None:
        self.prefix = prefix
        self.min_df = min_df
        self.vocabulary_: dict[str, int] = {}
        self.idf_: dict[str, float] = {}

    def fit(self, documents: list[list[str]]) -> "TfidfVectorizer":
        document_frequency: Counter[str] = Counter()
        for document in documents:
            for token in set(document):
                document_frequency[token] += 1
        doc_count = max(1, len(documents))
        tokens = [
            token
            for token, df_value in sorted(document_frequency.items())
            if df_value >= self.min_df
        ]
        self.vocabulary_ = {token: index for index, token in enumerate(tokens)}
        self.idf_ = {
            token: log((1.0 + doc_count) / (1.0 + document_frequency[token])) + 1.0
            for token in self.vocabulary_
        }
        return self

    def transform(self, documents: list[list[str]]) -> list[dict[str, float]]:
        rows: list[dict[str, float]] = []
        for document in documents:
            counts = Counter(token for token in document if token in self.vocabulary_)
            total = sum(counts.values())
            if total <= 0:
                rows.append({})
                continue
            features = {
                f"{self.prefix}:{token}": (count / total) * self.idf_[token]
                for token, count in counts.items()
            }
            rows.append(features)
        return rows

    def fit_transform(self, documents: list[list[str]]) -> list[dict[str, float]]:
        self.fit(documents)
        return self.transform(documents)
