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
    """Store the normalized URL view derived from one raw URL input.

    Attributes:
        original_url: Raw URL string received from the caller.
        normalized_url: Cleaned URL with normalized casing/path shape and
            stripped tracking parameters.
        domain: Lower-cased network location used for later filtering and
            persistence.
    """

    original_url: str
    normalized_url: str
    domain: str


@dataclass(slots=True)
class BlogIdentityResolution:
    """Describe the canonical identity inferred from one homepage-like URL.

    Attributes:
        original_url: Raw URL string passed into identity resolution.
        normalized_url: Cleaned URL produced by ``normalize_url`` before
            homepage-specific collapsing rules are applied.
        domain: Lower-cased network location from the normalized URL.
        canonical_host: Host chosen as the stable site identity host.
        canonical_path: Path chosen as the stable site identity path.
        canonical_url: Canonical homepage-like URL built from the host/path
            identity rules.
        identity_key: Stable persistence key used to group equivalent blog URLs.
        matched_rules: Human-readable list of rules applied during resolution.
        reason_codes: Machine-friendly reason codes describing the same rules.
        ruleset_version: Version identifier for the active identity ruleset.
        is_homepage: Whether the normalized URL was treated as homepage-like and
            therefore eligible for host-collapsing rules.
    """

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
    """Normalize one URL for crawler deduplication and persistence.

    Args:
        url: Raw URL string discovered from seeds, HTML extraction, or user
            input.

    Returns:
        A ``NormalizedUrl`` containing the cleaned URL, original input, and
        lower-cased domain.
    """
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
    # This layer is intentionally lightweight: it keeps the URL stable for
    # deduplication without trying to infer whether two homepages are the same site.
    query = urlencode(query_items)
    normalized = urlunparse((scheme, netloc, path, "", query, ""))
    return NormalizedUrl(original_url=url, normalized_url=normalized, domain=netloc)


def _normalized_path(parsed: ParseResult) -> str:
    """Return a stable path string for one parsed URL.

    Args:
        parsed: Parsed URL components from ``urlparse``.

    Returns:
        A normalized path string with empty paths converted to ``/`` and
        non-root trailing slashes removed.
    """
    path = parsed.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    if not path:
        return "/"
    return path


def _collapse_homepage_path(path: str) -> tuple[str, list[str]]:
    """Collapse homepage aliases such as ``/index.html`` to ``/``.

    Args:
        path: Normalized URL path to inspect.

    Returns:
        A tuple of ``(canonical_path, applied_rules)`` where ``applied_rules``
        records any homepage-path normalization performed.
    """
    if path.lower() in DEFAULT_HOMEPAGE_PATHS:
        rules = ["default_homepage_path_collapsed"] if path != "/" else []
        return "/", rules
    return path, []


def _registrable_domain(host: str) -> str:
    """Estimate the registrable root domain for one host string.

    Args:
        host: Lower-cased hostname whose effective registrable domain should be
            inferred.

    Returns:
        The registrable domain portion used by later tenant-subdomain checks.
    """
    labels = [label for label in host.split(".") if label]
    if len(labels) <= 2:
        return host
    suffix = ".".join(labels[-2:])
    if suffix in COMMON_MULTIPART_PUBLIC_SUFFIXES and len(labels) >= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def _looks_like_tenant_subdomain_label(label: str) -> bool:
    """Check whether one subdomain label looks tenant-like rather than generic.

    Args:
        label: Single hostname label located before the registrable domain.

    Returns:
        ``True`` when the label looks like a user/tenant identifier that may be
        safely collapsed to the registrable root.
    """
    normalized = label.strip().lower()
    if normalized in BLOG_HOST_ALIAS_PREFIXES or normalized in NON_TENANT_SUBDOMAIN_LABELS:
        return False
    return bool(TENANT_SUBDOMAIN_PATTERN.fullmatch(normalized))


def _supports_tenant_root_collapse(registrable_domain: str) -> bool:
    """Decide whether one registrable domain is eligible for tenant collapsing.

    Args:
        registrable_domain: Registrable root domain being evaluated.

    Returns:
        ``True`` when the domain appears to host tenant-like subdomains that the
        crawler should merge into one root homepage identity.
    """
    if registrable_domain in TENANT_ROOT_COLLAPSE_EXCLUDED_REGISTRABLE_DOMAINS:
        return False
    labels = [label for label in registrable_domain.split(".") if label]
    if len(labels) < 2:
        return False
    return len(labels[-1]) == 2


def _collapse_homepage_host(host: str) -> tuple[str, list[str]]:
    """Collapse safe homepage host aliases into one canonical host.

    Args:
        host: Lower-cased hostname from a homepage-like URL.

    Returns:
        A tuple of ``(canonical_host, applied_rules)`` describing any alias or
        tenant-subdomain collapses that were applied.
    """
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
    """Resolve one URL into a stable, explainable blog identity.

    Args:
        url: Raw URL string representing a blog homepage or page.

    Returns:
        A ``BlogIdentityResolution`` describing the canonical host/path identity
        used to merge equivalent blog records in persistence.
    """
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
        # Host collapsing is intentionally homepage-only so article/detail URLs
        # do not get merged into a site's root identity by accident.
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
