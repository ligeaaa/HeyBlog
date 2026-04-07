"""Normalize and sanitize URLs before persistence and deduplication."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import ParseResult
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse


TRACKING_PARAMS = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "spm",
    "ref",
}
BLOG_HOST_ALIAS_PREFIXES = ("www", "blog")
DEFAULT_HOMEPAGE_PATHS = ("/", "/index.html", "/index.htm")
IDENTITY_RULESET_VERSION = "2026-04-05-v1"


@dataclass(slots=True)
class NormalizedUrl:
    """Normalized URL values derived from one raw input URL."""

    original_url: str
    normalized_url: str
    domain: str


@dataclass(slots=True)
class BlogIdentityResolution:
    """Identity resolution derived from one homepage-like URL."""

    original_url: str
    normalized_url: str
    domain: str
    canonical_host: str
    canonical_path: str
    identity_key: str
    matched_rules: list[str]
    reason_codes: list[str]
    ruleset_version: str
    is_homepage: bool


def normalize_url(url: str) -> NormalizedUrl:
    """Normalize scheme, host casing, path and remove tracking params."""
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


def _normalized_path(parsed: ParseResult) -> str:
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not path:
        return "/"
    return path


def _collapse_homepage_path(path: str) -> tuple[str, list[str]]:
    if path.lower() in DEFAULT_HOMEPAGE_PATHS:
        rules = ["default_homepage_path_collapsed"] if path != "/" else []
        return "/", rules
    return path, []


def resolve_blog_identity(url: str) -> BlogIdentityResolution:
    """Resolve one URL into a stable, explainable blog identity."""
    normalized = normalize_url(url)
    parsed = urlparse(normalized.normalized_url)
    host = parsed.netloc.lower()
    path = _normalized_path(parsed)
    canonical_path, path_rules = _collapse_homepage_path(path)
    is_homepage = canonical_path == "/"
    canonical_host = host
    rules: list[str] = []
    reason_codes: list[str] = []

    if parsed.scheme.lower() in {"http", "https"}:
        rules.append("scheme_ignored")
        reason_codes.append("scheme_ignored")

    if is_homepage:
        reason_codes.extend(path_rules)
        rules.extend(path_rules)
        parts = host.split(".")
        if len(parts) > 2 and parts[0] in BLOG_HOST_ALIAS_PREFIXES:
            alias = parts[0]
            canonical_host = ".".join(parts[1:])
            rule_name = f"{alias}_alias_collapsed"
            rules.append(rule_name)
            reason_codes.append(rule_name)

    identity_key = f"site:{canonical_host}{canonical_path}"
    return BlogIdentityResolution(
        original_url=url,
        normalized_url=normalized.normalized_url,
        domain=normalized.domain,
        canonical_host=canonical_host,
        canonical_path=canonical_path,
        identity_key=identity_key,
        matched_rules=rules,
        reason_codes=reason_codes,
        ruleset_version=IDENTITY_RULESET_VERSION,
        is_homepage=is_homepage,
    )
