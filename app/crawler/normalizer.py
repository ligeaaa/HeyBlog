from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "ref",
}


@dataclass(slots=True)
class NormalizedUrl:
    original_url: str
    normalized_url: str
    domain: str


def normalize_url(url: str) -> NormalizedUrl:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(query_items)
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return NormalizedUrl(original_url=url, normalized_url=normalized, domain=netloc)
