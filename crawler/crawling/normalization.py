"""Normalize and sanitize URLs before persistence and deduplication."""

from __future__ import annotations

from dataclasses import dataclass
import re
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
COMMON_MULTIPART_PUBLIC_SUFFIXES = frozenset(
    {
        "ac.cn",
        "ac.uk",
        "co.jp",
        "co.uk",
        "com.au",
        "com.cn",
        "com.hk",
        "com.tw",
        "edu.cn",
        "gov.cn",
        "gov.uk",
        "mil.cn",
        "net.au",
        "net.cn",
        "net.tw",
        "org.au",
        "org.cn",
        "org.tw",
    }
)
TENANT_ROOT_COLLAPSE_EXCLUDED_REGISTRABLE_DOMAINS = frozenset(
    {
        "gitee.io",
        "github.io",
    }
)
NON_TENANT_SUBDOMAIN_LABELS = frozenset(
    {
        "admin",
        "api",
        "app",
        "assets",
        "bbs",
        "beta",
        "cdn",
        "cn",
        "demo",
        "dev",
        "docs",
        "en",
        "forum",
        "ftp",
        "help",
        "img",
        "m",
        "mail",
        "mobile",
        "news",
        "open",
        "shop",
        "static",
        "status",
        "support",
        "wiki",
        "www2",
        "zh",
    }
)
TENANT_SUBDOMAIN_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{4,30}[a-z0-9]$")
IDENTITY_RULESET_VERSION = "2026-04-07-v5"


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
    canonical_url: str
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


def _registrable_domain(host: str) -> str:
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return host
    suffix = ".".join(labels[-2:])
    if suffix in COMMON_MULTIPART_PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _looks_like_tenant_subdomain_label(label: str) -> bool:
    normalized = label.strip().lower()
    if normalized in BLOG_HOST_ALIAS_PREFIXES or normalized in NON_TENANT_SUBDOMAIN_LABELS:
        return False
    return bool(TENANT_SUBDOMAIN_PATTERN.fullmatch(normalized))


def _supports_tenant_root_collapse(registrable_domain: str) -> bool:
    if registrable_domain in TENANT_ROOT_COLLAPSE_EXCLUDED_REGISTRABLE_DOMAINS:
        return False
    labels = [label for label in registrable_domain.split(".") if label]
    if len(labels) < 2:
        return False
    return len(labels[-1]) == 2


def _collapse_homepage_host(host: str) -> tuple[str, list[str]]:
    canonical_host = host
    rules: list[str] = []
    parts = canonical_host.split(".")
    if len(parts) > 2 and parts[0] in BLOG_HOST_ALIAS_PREFIXES:
        alias = parts[0]
        canonical_host = ".".join(parts[1:])
        rules.append(f"{alias}_alias_collapsed")

    registrable_domain = _registrable_domain(canonical_host)
    if canonical_host != registrable_domain and _supports_tenant_root_collapse(registrable_domain):
        label_count = len([label for label in canonical_host.split(".") if label])
        registrable_count = len([label for label in registrable_domain.split(".") if label])
        subdomain_labels = canonical_host.split(".")[: label_count - registrable_count]
        if len(subdomain_labels) == 1 and _looks_like_tenant_subdomain_label(subdomain_labels[0]):
            canonical_host = registrable_domain
            rules.append("tenant_subdomain_collapsed")

    return canonical_host, rules


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
        canonical_host, host_rules = _collapse_homepage_host(host)
        rules.extend(host_rules)
        reason_codes.extend(host_rules)

    canonical_url = urlunparse(("https", canonical_host, canonical_path, "", "", ""))
    identity_key = f"site:{canonical_host}{canonical_path}"
    return BlogIdentityResolution(
        original_url=url,
        normalized_url=normalized.normalized_url,
        domain=normalized.domain,
        canonical_host=canonical_host,
        canonical_path=canonical_path,
        canonical_url=canonical_url,
        identity_key=identity_key,
        matched_rules=rules,
        reason_codes=reason_codes,
        ruleset_version=IDENTITY_RULESET_VERSION,
        is_homepage=is_homepage,
    )
