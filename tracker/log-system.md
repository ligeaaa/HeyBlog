# Unified Logging System

Created: 2026-05-24

## Background

The project had crawler-only lifecycle logs, legacy no-op database log endpoints,
and task-specific maintenance events. The goal is to build one shared logging
system used by every service, with unified fields, service-specific directories,
separate files for review, and moderate event granularity.

## Goals

- Use one shared module for Python service logging.
- Write readable service-specific files under a common root.
- Keep application, error, and access logs separate.
- Carry request ids across frontend, backend, crawler, search, and persistence.
- Keep domain maintenance events separate from application logs.
- Avoid new dependencies unless explicitly requested.

## Decisions

- Use Python standard `logging` rather than adding `structlog` or `loguru`.
- Default to JSON lines for production-friendly parsing.
- Store local logs under `logs/{app,error,access}/<service>/` as hourly
  service slices, and Docker logs under `volumes/logs/{app,error,access}/<service>/`.
- Preserve `/internal/logs` as a legacy no-op compatibility endpoint.
- Keep URL refilter and blog dedup progress as persisted domain events.

## Progress

- Added `shared.observability` with logging setup, JSON formatter, request-id
  middleware, access logging, and event helper.
- Added log configuration fields to `Settings`.
- Wired backend, crawler, persistence-api, search, and frontend service entrypoints.
- Added `x-request-id` propagation through frontend proxy and shared HTTP clients.
- Migrated crawler lifecycle logs and model-consensus warnings to stable events.
- Updated Docker Compose to mount shared log volume.
- Updated API/config/architecture documentation and `.env` / `.env.example`.
- Added observability regression tests.

## Validation

- Passed: `./.venv/bin/pytest tests/test_observability_logging.py tests/test_crawler_service.py tests/test_service_split.py::test_persistence_service_exposes_supported_repository_data tests/test_service_split.py::test_backend_url_refilter_run_stops_crawler_and_persists_progress_events`
- Passed: `./.venv/bin/pytest tests/test_observability_logging.py tests/test_service_split.py tests/test_pipeline.py tests/test_crawler_model_consensus.py`
- Passed: `./.venv/bin/pytest` (`152 passed`)
- Verified by tests: type-specific hourly log directories, JSON fields, request-id middleware, and shared HTTP client propagation.

## Closure

Completed on 2026-05-24. The logging system now has a shared implementation,
service entrypoint integration, Docker volume routing, documentation, and
regression coverage.

Update 2026-05-24: log files now group by type first (`app`, `error`,
`access`), then by service, slice hourly using `<service>-YYYYMMDD-HH.log`,
delete slices older than `HEYBLOG_LOG_RETENTION_DAYS`, and expose those settings
in `.env` and `.env.example`.

## Remaining Risks

- Uvicorn's own access logger still exists unless deployment disables or
  redirects it; HeyBlog now writes its own normalized access hourly slices.
- This pass does not implement audit logs or metrics; the boundaries are
  documented for future work.
