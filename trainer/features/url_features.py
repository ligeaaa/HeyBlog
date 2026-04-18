"""URL feature extraction for structured and text baselines."""

from __future__ import annotations

import re
from urllib.parse import urlparse

from trainer.constants import URL_KEYWORDS

TOKEN_SPLIT_PATTERN = re.compile(r"[^0-9a-z\u4e00-\u9fff]+", re.IGNORECASE)


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def tokenize_url(normalized_url: str) -> list[str]:
    parsed = urlparse(normalized_url)
    source = " ".join(
        [
            parsed.netloc,
            parsed.path.replace("/", " "),
            parsed.query.replace("&", " "),
        ]
    ).lower()
    tokens = [token for token in TOKEN_SPLIT_PATTERN.split(source) if token]
    return tokens


def extract_url_features(normalized_url: str) -> dict[str, float]:
    parsed = urlparse(normalized_url)
    host_labels = [label for label in parsed.netloc.split(".") if label]
    path_segments = [segment for segment in parsed.path.split("/") if segment]
    path_text = " ".join(path_segments).lower()
    query_present = 1.0 if bool(parsed.query) else 0.0
    digit_count = sum(1 for char in normalized_url if char.isdigit())
    features = {
        "url:path_depth": float(len(path_segments)),
        "url:path_length": float(len(parsed.path)),
        "url:is_root_path": 1.0 if parsed.path in {"", "/"} else 0.0,
        "url:has_query": query_present,
        "url:subdomain_count": float(max(0, len(host_labels) - 2)),
        "url:url_length": float(len(normalized_url)),
        "url:domain_length": float(len(parsed.netloc)),
        "url:hyphen_count": float(normalized_url.count("-")),
        "url:underscore_count": float(normalized_url.count("_")),
        "url:digit_ratio": _safe_ratio(digit_count, len(normalized_url)),
    }
    for keyword in URL_KEYWORDS:
        features[f"url:kw:{keyword}"] = 1.0 if keyword in path_text or keyword in parsed.netloc.lower() else 0.0
    return features


def url_char_ngrams(normalized_url: str, min_n: int, max_n: int) -> list[str]:
    text = normalized_url.lower().strip()
    if not text:
        return []
    tokens: list[str] = []
    for width in range(min_n, max_n + 1):
        if len(text) < width:
            continue
        for index in range(0, len(text) - width + 1):
            tokens.append(text[index : index + width])
    if not tokens:
        return [text]
    return tokens
