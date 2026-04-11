"""Title cleaning, tokenization, and structured features."""

from __future__ import annotations

import re
import unicodedata

from trainer.constants import TITLE_KEYWORDS

TITLE_TOKEN_PATTERN = re.compile(r"[0-9A-Za-z\u4e00-\u9fff]+")


def clean_title(title: str) -> str:
    normalized = unicodedata.normalize("NFKC", title or "").strip().lower()
    return " ".join(normalized.split())


def tokenize_title(title: str) -> list[str]:
    cleaned = clean_title(title)
    return TITLE_TOKEN_PATTERN.findall(cleaned)


def title_word_ngrams(tokens: list[str], min_n: int, max_n: int) -> list[str]:
    if not tokens:
        return []
    grams: list[str] = []
    for width in range(min_n, max_n + 1):
        if len(tokens) < width:
            continue
        for index in range(0, len(tokens) - width + 1):
            grams.append(" ".join(tokens[index : index + width]))
    return grams or list(tokens)


def extract_title_features(title: str) -> dict[str, float]:
    cleaned = clean_title(title)
    tokens = tokenize_title(cleaned)
    features = {
        "title:missing": 1.0 if not cleaned else 0.0,
        "title:length": float(len(cleaned)),
        "title:token_count": float(len(tokens)),
        "title:avg_token_length": (sum(len(token) for token in tokens) / len(tokens)) if tokens else 0.0,
    }
    for keyword in TITLE_KEYWORDS:
        features[f"title:kw:{keyword}"] = 1.0 if keyword in cleaned else 0.0
    return features
