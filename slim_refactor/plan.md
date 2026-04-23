# Slim Refactor Plan

## 1. Context

- date: 2026-04-23
- repo_path: `/Users/lige/code/HeyBlog`
- scope: project-wide strict-mode convergence rounds, currently covering backend, crawler, and bounded persistence repository hotspots
- objective: reduce duplicated internal logic without changing intended current backend or crawler contracts
- constraints:
  - preserve public/admin/backend response semantics documented in `doc/api-docs.md`
  - preserve legacy crawler filter API behavior exposed by `crawler.filters`
  - preserve current assertion strictness in regression tests
  - prefer deletion/convergence over new abstraction layers

## 2. Current Problems (Proven Only)

List only verified issues:
- redundant module or logic:
  - `backend/main.py` repeats upstream `httpx.HTTPStatusError` detail extraction and rethrow logic across many routes.
  - `backend/main.py` repeats URL refilter failure-marking branches with near-identical `try/except/pass` bodies.
  - `crawler/filters.py` and `crawler/crawling/decisions/filters.py` both implement the same blocked-domain and exact-URL matcher logic.
  - `persistence_api/repository.py` repeats pagination-count / effective-page / offset calculation in both `list_blogs_catalog()` and `list_blog_labeling_candidates()`.
  - `persistence_api/repository.py` repeats `session.scalar(select(func.count()).select_from(...))` for the same internal counting pattern across pagination, stats, refilter bookkeeping, dedup bookkeeping, and reset reporting.
- state forks:
  - backend maintenance failure handling is expressed in multiple branches, increasing the chance that one path forgets to reset `maintenance_in_progress` or mark a run failed.
- over-abstraction:
  - none targeted this round; existing compatibility shims stay intact unless proven removable without contract loss.
- hidden behavior:
  - backend error translation currently hides its intended policy inside repeated inline blocks instead of a single helper path.
  - repository pagination semantics are currently encoded inline in multiple query methods instead of a single helper.
- unnecessary config paths:
  - none targeted this round.

## 3. Minimal Closed Loop to Keep

Define the smallest still-working behavior that must remain valid:
- required capability 1: backend routes must continue forwarding upstream status/detail correctly for public and admin APIs.
- required capability 2: crawler rule-based URL candidate filtering must keep current accept/reject reasons and legacy helper API behavior.
- required capability 3: persistence catalog and blog-labeling endpoints must keep current pagination, filters, and counting semantics.

## 4. Contract Invariants

Record the intended current contract that must remain valid:
- backend behavior invariants:
  - route URLs, auth gates, maintenance semantics, and background task lifecycle remain unchanged.
  - upstream `httpx.HTTPStatusError` responses still surface the upstream status code and `detail` payload when available.
- response semantics invariants:
  - existing JSON payload shapes for backend routes remain unchanged.
  - crawler `decide_blog_candidate()` keeps the same reason codes and acceptance outcomes for identical inputs.
  - repository catalog and labeling payloads keep current `page`, `page_size`, `total_items`, `total_pages`, `has_next`, `has_prev`, `filters`, and `available_tags` semantics.
- assertion standards that must not be weakened:
  - do not relax tests by broadening accepted status codes, loosening payload assertions, or masking failures.

## 5. Planned Convergence Actions

Use action IDs for traceability.

| Action ID | Type (`remove` / `merge` / `simplify` / `keep`) | Target module or file | First-principles reason | Risk |
|---|---|---|---|---|
| A1 | merge | `crawler/filters.py`, `crawler/crawling/decisions/filters.py` | One filtering contract should share one predicate implementation for exact-url and blocked-domain matching. | low |
| A2 | simplify | `backend/main.py` | One backend should translate upstream HTTP errors through one helper path instead of many copy-pasted blocks. | medium |
| A3 | simplify | `backend/main.py` | URL refilter failure marking should be handled through one helper to reduce branch drift. | medium |
| A4 | keep | compatibility shim modules under `services/` and `backend/` | Existing tests prove these remain part of the intended current contract, so they are explicitly out of scope. | low |
| A5 | simplify | `persistence_api/repository.py` | One repository should count rows through one helper path instead of repeating raw scalar count expressions. | low |
| A6 | simplify | `persistence_api/repository.py` | Catalog and labeling queries should share one pagination execution helper so effective-page semantics cannot drift. | low |

## 6. Target Structure (After This Round)

Describe concise structure after convergence:
- module boundaries:
  - crawler rule helpers live in a single shared internal helper module used by both legacy and filter-chain entrypoints.
  - backend upstream error conversion and url-refilter failure marking each have one internal helper path.
  - repository count and pagination utilities live in small internal helpers used by catalog, labeling, stats, and maintenance flows.
- key data and control path:
  - route handlers call small helpers for upstream error conversion rather than reimplementing JSON/detail extraction.
  - legacy crawler filter API delegates shared predicates instead of carrying duplicate matcher logic.
  - repository paginated queries ask one helper to compute total items, effective page, offset, and rows.
- removed branches:
  - repeated backend error-detail extraction blocks
  - repeated URL refilter failure-marking branches
  - repeated crawler predicate helper implementations
  - repeated repository count/pagination bookkeeping blocks

## 7. Validation Plan

- automated commands:
  - `pytest tests/test_filters.py tests/test_service_split.py`
  - `python -m compileall backend crawler`
  - `./.venv/bin/pytest tests/test_repository.py`
  - `python3 -m compileall persistence_api`
- manual smoke checks (if needed):
  - none expected if targeted tests stay green
- pass criteria:
  - targeted tests pass with unchanged contract assertions
  - touched modules compile cleanly
- mismatch indicators that require the contract-mismatch gate:
  - changed status code/detail propagation in backend tests
  - changed crawler filter reason codes or acceptance decisions in tests
  - changed repository pagination metadata or count semantics in repository tests

## 8. Contract-Mismatch Gate Plan

If validation suggests backend/test disagreement:
- reviewer type: `local_fallback`
- classification result:
- allowed stale-test action: update affected tests or skip those tests for this round
- required follow-up if stale tests are left behind: record exact scope in `slim_refactor/report.md` and `tracker/project-slim-refactor-20260423.md`

## 9. Change Guardrail

Allow only actions declared in this plan.
If new action is required, update this plan first and then implement code changes.
