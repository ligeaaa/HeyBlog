"""Filter extracted links to keep only deterministic external blog homepages."""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from crawler.crawling.decisions.rule_helpers import BLOCKED_TLDS
from crawler.crawling.decisions.rule_helpers import FILE_SUFFIX_BLOCKLIST
from crawler.crawling.decisions.rule_helpers import PATH_BLOCKLIST
from crawler.crawling.decisions.rule_helpers import PLATFORM_BLOCKLIST
from crawler.crawling.decisions.rule_helpers import has_asset_suffix
from crawler.crawling.decisions.rule_helpers import has_extra_location_parts
from crawler.crawling.decisions.rule_helpers import is_root_like_path
from crawler.crawling.decisions.rule_helpers import matches_blocked_domain
from crawler.crawling.decisions.rule_helpers import matches_exact_url
from crawler.crawling.decisions.rule_helpers import matches_prefix_blocklist
from crawler.crawling.decisions.rule_helpers import path_has_blocked_segment


@dataclass
class LinkDecision:
    """Describe the deterministic outcome of evaluating one extracted link.

    Attributes:
        accepted: Whether the candidate passed the crawler's hard filtering
            rules and should continue as a blog candidate.
        score: Legacy scoring field preserved for compatibility with older
            decision interfaces. The current rules use hard accept/reject logic,
            so this value remains ``0.0``.
        reasons: Machine-readable reason codes explaining why the link was
            accepted or rejected.
        hard_blocked: Whether the link was rejected by a non-recoverable hard
            rule rather than a softer heuristic.
    """

    accepted: bool
    score: float
    reasons: tuple[str, ...]
    hard_blocked: bool = False

def decide_blog_candidate(
    url: str,
    source_domain: str,
    *,
    link_text: str = "",
    context_text: str = "",
    domain_blocklist: tuple[str, ...] = (),
    blocked_tlds: tuple[str, ...] = BLOCKED_TLDS,
    exact_url_blocklist: tuple[str, ...] = (),
    prefix_blocklist: tuple[str, ...] = (),
) -> LinkDecision:
    """Classify whether an extracted link should be treated as a blog homepage.

    Args:
        url: Absolute extracted URL being evaluated.
        source_domain: Domain of the page where the link was discovered.
        link_text: Visible anchor text associated with the link. Kept for API
            compatibility even though the current rules do not use it.
        context_text: Nearby container text associated with the link. Kept for
            compatibility with richer decision strategies.
        domain_blocklist: Additional blocked domains supplied by crawler
            configuration.
        blocked_tlds: TLD suffixes that should always be rejected.
        exact_url_blocklist: Explicit absolute URLs that should be rejected.
        prefix_blocklist: URL prefixes that should be rejected before any other
            acceptance logic runs.

    Returns:
        A ``LinkDecision`` describing whether the link survives the crawler's
        hard homepage filters and, if not, which rule rejected it.
    """
    parsed = urlparse(url)
    domain = parsed.netloc.lower()
    normalized_source_domain = source_domain.lower()
    normalized_url = url.rstrip("/")
    path = parsed.path.lower() or "/"
    score = 0.0

    # Apply hard blocks first so clearly invalid candidates never reach the softer scoring layer.
    if not parsed.scheme.startswith("http"):
        return LinkDecision(False, score, ("non_http_scheme",), hard_blocked=True)
    if not domain or domain == normalized_source_domain:
        return LinkDecision(False, score, ("same_domain",), hard_blocked=True)
    if matches_exact_url(normalized_url, exact_url_blocklist):
        return LinkDecision(False, score, ("exact_url_blocked",), hard_blocked=True)
    if matches_prefix_blocklist(normalized_url, prefix_blocklist):
        return LinkDecision(False, score, ("prefix_blocked",), hard_blocked=True)
    if matches_blocked_domain(domain, PLATFORM_BLOCKLIST):
        return LinkDecision(False, score, ("platform_blocked",), hard_blocked=True)
    if matches_blocked_domain(domain, domain_blocklist):
        return LinkDecision(False, score, ("domain_blocked",), hard_blocked=True)
    if any(domain.endswith(tld) for tld in blocked_tlds):
        return LinkDecision(False, score, ("blocked_tld",), hard_blocked=True)
    # Friend-link directories usually point to the target blog homepage rather than
    # a deep article or section path, so we keep only root URLs here.
    if not is_root_like_path(parsed.path):
        return LinkDecision(False, score, ("non_root_path",), hard_blocked=True)
    if has_extra_location_parts(query=parsed.query, fragment=parsed.fragment):
        return LinkDecision(False, score, ("non_root_location",), hard_blocked=True)
    if has_asset_suffix(path):
        return LinkDecision(False, score, ("asset_suffix",), hard_blocked=True)
    if path_has_blocked_segment(path):
        return LinkDecision(False, score, ("blocked_path",), hard_blocked=True)

    # Passing all hard rules is now sufficient for acceptance.
    return LinkDecision(True, score, ("passed_hard_filters",), hard_blocked=False)


def is_blog_candidate(url: str, source_domain: str) -> bool:
    """Return whether an extracted URL passes the default blog candidate rules.

    Args:
        url: Absolute extracted URL being evaluated.
        source_domain: Domain of the source page that contained the link.

    Returns:
        ``True`` when ``decide_blog_candidate`` accepts the URL.
    """
    return decide_blog_candidate(url, source_domain).accepted
