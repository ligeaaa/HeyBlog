---
name: filter-chain-two-phase-architecture
description: How the crawler URL filter chain works after the 2026-05-30 RSS refactor (rule AND-gate + success OR-group)
metadata:
  type: project
---

As of 2026-05-30 the crawler URL decision chain ([crawler/crawling/decisions/chain.py](crawler/crawling/decisions/chain.py)) is two-phase, not the old pure-AND chain:

- **Phase 1 — `rule` filters (AND-gate):** every deterministic hard rule must accept; first rejection wins and returns verbatim. `decider_role == "rule"`.
- **Phase 2 — `success` deciders (ordered OR-group):** run after rules. First decider that *confirms* (returns `FilterDecision.confirmed=True`) keeps the candidate immediately, carrying any `feed_url`. A decider that *abstains* (accepts without confirming) defers to the next. If none confirm but at least one rejected, the last rejection wins. `decider_role == "success"`.

Success deciders in default order: `rss_discovery` then `model_consensus`.

- **RSS layer** ([crawler/crawling/decisions/rss.py](crawler/crawling/decisions/rss.py)): fetches the candidate homepage, parses `<link rel=alternate>` feed links, probes common feed paths, validates with `feedparser`. Confirms + records the feed URL. **Needs a live fetcher** threaded via `UrlCandidateContext.fetcher` (+ `fetch_deadline`). Offline callers (dedup scan, funnel stats) pass no fetcher, so RSS abstains and stays network-free. Flag: `HEYBLOG_RSS_DISCOVERY_ENABLED` (default on).
- RSS-absence is an **abstain**, never a rejection — many blogs lack feeds, so they fall through to model consensus. With RSS off, behavior is identical to the legacy chain.

`feed_url` is persisted on `blogs.feed_url` via `upsert_blog(..., feed_url=...)` (only set on insert or when existing feed is empty; never overwritten with null).

**The offline URL-refilter feature was deleted entirely** in the same change (per user request): all `url_refilter` repository methods/models/endpoints/HTTP-client methods/frontend UI, plus `_backup_sqlite_database`, `_handle_refilter_*`, `_filter_chain_version`. The blog **dedup scan** is a separate feature and was kept — it still uses `decision_chain.decide()`, `_decision_scan_settings`, `_decision_scan_ruleset_version`, `_delete_blog_graph`. Migration `20260530_02` drops the refilter tables; `20260530_01` adds `feed_url`. Related: [[heyblog-service-boundaries]].
