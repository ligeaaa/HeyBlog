"""Compose feature maps for the supported baselines."""

from __future__ import annotations

from trainer.dataset.schema import SupervisedSample
from trainer.features.title_features import extract_title_features
from trainer.features.title_features import title_word_ngrams
from trainer.features.title_features import tokenize_title_char_chunks
from trainer.features.url_features import extract_url_features
from trainer.features.url_features import tokenize_url
from trainer.features.url_features import url_char_ngrams


def merge_feature_maps(*maps: dict[str, float]) -> dict[str, float]:
    """Merge multiple sparse feature maps into one row."""
    merged: dict[str, float] = {}
    for item in maps:
        merged.update(item)
    return merged


def build_structured_feature_rows(samples: list[SupervisedSample]) -> list[dict[str, float]]:
    """Build one structured feature dictionary per supervised sample."""
    rows: list[dict[str, float]] = []
    for sample in samples:
        rows.append(
            merge_feature_maps(
                extract_url_features(sample.normalized_url),
                extract_title_features(sample.title),
            )
        )
    return rows


def build_tfidf_documents(
    samples: list[SupervisedSample],
    *,
    url_char_ngram_range: tuple[int, int],
    title_word_ngram_range: tuple[int, int],
    title_token_chunk_size: int,
) -> tuple[list[list[str]], list[list[str]]]:
    """Build token documents for the dual URL/title TF-IDF baselines."""
    url_docs: list[list[str]] = []
    title_docs: list[list[str]] = []
    for sample in samples:
        url_docs.append(url_char_ngrams(sample.normalized_url, *url_char_ngram_range) + tokenize_url(sample.normalized_url))
        title_tokens = tokenize_title_char_chunks(sample.title, title_token_chunk_size)
        title_docs.append(title_word_ngrams(title_tokens, *title_word_ngram_range))
    return url_docs, title_docs
