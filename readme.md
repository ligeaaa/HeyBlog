# HeyBlog

HeyBlog is an MVP crawler for the blog friend-link ecosystem. It starts from a set
of seed blog URLs, discovers friend-link pages, extracts outbound blog links,
stores the resulting graph in SQLite for local monolith mode, and now ships with
a split-service runtime topology for frontend, backend, crawler, search,
`persistence-api`, and `persistence-db` Postgres workloads.

## Current MVP Scope

- Seed import from `seed.csv`
- SQLite-backed persistence for blogs, edges, and crawl logs
- HTTP-first crawl flow with friend-link discovery and extraction
- REST APIs for status, blogs, blog detail, edges, graph, stats, and logs
- Export support for `nodes.csv`, `edges.csv`, and `graph.json`

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
python -m uvicorn backend.main:app --reload
```

The backend API will be available at `http://127.0.0.1:8000`, with interactive
docs at `/docs`.

The split frontend panel is available at `http://127.0.0.1:3000/` when the
frontend service is running. The runtime now uses the split topology with
`persistence-api + persistence-db`.

## Seed Blogs

The initial seed list in `seed.csv` contains:

- `https://blog.elykia.cn/`
- `https://www.qladgk.com/`
- `https://www.imaegoo.com/`

## Suggested Flow

1. Start the frontend, backend, crawler, search, persistence-api, and persistence-db services.
2. Call `POST /api/crawl/bootstrap` through the frontend or backend.
3. Call `POST /api/crawl/run` to process pending blogs.
4. Use the read APIs to inspect status, nodes, edges, stats, logs, and search.
5. Read exported graph artifacts under `volumes/exports/`.

## Docker

```bash
docker compose up --build
```

This starts:

- `frontend` on `http://127.0.0.1:3000`
- `backend` on `http://127.0.0.1:8000`
- `crawler` on `http://127.0.0.1:8010`
- `search` on `http://127.0.0.1:8020`
- `persistence-api` on `http://127.0.0.1:8030`
- `persistence-db` (PostgreSQL) on `127.0.0.1:5432`

The split services communicate over the shared Docker network and persist data to:

- `./volumes/postgres`
- `./volumes/exports`
- `./volumes/search-cache`

## Tests

The repository keeps tests centralized under `tests/`. New tests should prefer
importing from the top-level packages such as `crawler/`, `backend/`, `search/`,
`persistence_api/`, `frontend/`, and `shared/`.

## Shared Boundary

`shared/` is intentionally narrow. Only stable, cross-service utilities belong
there:

- runtime configuration
- small reusable HTTP clients
- pure data helpers or contracts

Do not place service-specific business logic in `shared/`. If code only serves
one deployable unit, it should live in that service package instead.

## services/ Policy

`services/` is retained only as the thinnest startup compatibility layer.

- Allowed: service entrypoint shims such as `services/backend/main.py`
- Not allowed: new business logic, runtime state, repository code, crawler logic,
  or service-specific domain code

Current decision:

- Keep `services/*/main.py` as transitional entry shims for one migration window
- Do not add new non-entrypoint modules under `services/`
- Prefer top-level service packages (`backend/`, `crawler/`, `search/`,
  `persistence_api/`, `frontend/`) for all new implementation code
