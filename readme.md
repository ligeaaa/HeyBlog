# HeyBlog

HeyBlog is a split-service MVP for crawling the blog friend-link ecosystem. It starts
from `seed.csv`, discovers friend-link pages, extracts outbound blog links, stores the
resulting graph in SQLite or PostgreSQL, and serves a public discovery surface, a protected admin surface, and a public API on
top of `frontend` + `backend` + `crawler` + `search` + `persistence-api`.

## Runtime Model

The real implementation lives in the top-level service packages:

- `frontend/`
- `backend/`
- `crawler/`
- `search/`
- `persistence_api/`
- `shared/`
- `trainer/` for offline training / evaluation workflows

`services/` is only a compatibility shim layer for startup entrypoints. New business
logic should stay in the top-level service packages.

## Choose A Start Path

### 1. API-only / backend minimal path

Use this when you want to debug HTTP contracts or backend behavior without the browser
panel. The backend still depends on the three internal services, so the smallest useful
local stack is `persistence-api + crawler + search + backend`.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

Create local config once:

```bash
cp .env.example .env
```

Start the services in separate terminals:

```bash
python -m uvicorn persistence_api.main:app --reload --port 8030
```

```bash
python -m uvicorn crawler.main:app --reload --port 8010
```

```bash
python -m uvicorn search.main:app --reload --port 8020
```

```bash
python -m uvicorn backend.main:app --reload --port 8000
```

Then verify the public API:

```bash
curl http://127.0.0.1:8000/api/status
```

### 2. Docker split runtime

Use this when you want the full local topology, including the browser panel and
PostgreSQL-backed persistence:

```bash
docker compose up --build
```

If you set `HEYBLOG_DB_DSN` manually, use the SQLAlchemy psycopg v3 form:
`postgresql+psycopg://...`

Services and default ports:

- `frontend`: `http://127.0.0.1:3000`
- `backend`: `http://127.0.0.1:8000`
- `crawler`: `http://127.0.0.1:8010`
- `search`: `http://127.0.0.1:8020`
- `persistence-api`: `http://127.0.0.1:8030`
- `persistence-db`: `127.0.0.1:5432`

Docker volumes persist runtime data under:

- `volumes/postgres`
- `volumes/exports`
- `volumes/search-cache`

### 3. Frontend development path

Use this when you are changing `frontend/src/` and want the public/admin SPA plus the real backend
API behind it.

Install frontend dependencies once:

```bash
cd frontend
npm install
```

Build the SPA bundle:

```bash
cd frontend
npm run build
```

Serve the built frontend against the local backend:

```bash
python -m uvicorn frontend.server:app --reload --port 3000
```

Current caveat: `frontend/src/lib/api.ts` uses same-origin `/api/*`, but
`frontend/vite.config.ts` does not currently define a dev proxy. If you run
`cd frontend && npm run dev`, you will need your own `/api` reverse proxy or mocked API.

### 4. Offline training baseline path

Use this when you want to run the `url + title` offline blog-classification baselines
against the exported labeling CSV:

```bash
python -m trainer.cli full-run --source-csv data/blog-label-training-2026-04-11.csv
```

Outputs are written under:

- `data/trainer/datasets/`
- `data/model/`

Runtime services do not read trainer output from `data/model/` directly.
Promote the model version you want to serve into:

- `runtime_resources/models/url_decision/current/`

Then keep local debug, tests, and Docker aligned by pointing
`HEYBLOG_DECISION_MODEL_ROOT` at that runtime resource path.

## Suggested Flow

1. Use the public surface for discovery: browse blogs, search, inspect graph, and submit ingestion requests.
2. Use the protected `/admin` surface for runtime control, manual crawl/bootstrap, labeling, dedup, and maintenance actions.
3. Read exported graph artifacts under `data/exports/` or `volumes/exports/`.

## Documentation Map

- [Project structure](doc/project-structure.md): directories, source-of-truth packages, and entrypoints
- [Services overview](doc/services-overview.md): service responsibilities, dependencies, and edit boundaries
- [Service architecture](doc/service-architecture.md): runtime call chains and data ownership
- [API docs](doc/api-docs.md): public, admin, and internal HTTP contracts
- [Config reference](doc/config-reference.md): environment variables, defaults, and service consumers
- [Developer workflows](doc/developer-workflows.md): where to start for common tasks
- [Graph/community PRD](doc/prd-graph-community-discovery.md): future product direction for graph analysis and community discovery
- [Public/admin boundary](doc/public-admin-boundary.md): route, API, and auth matrix for the split surfaces

## Development Rules

- If you change API routes, payload shapes, or calling patterns, update [doc/api-docs.md](doc/api-docs.md) in the same change.
- Prefer implementation changes in `backend/`, `crawler/`, `search/`, `persistence_api/`, and `frontend/`, not under `services/`.
- Keep `shared/` narrow: configuration, stable HTTP clients, and small cross-service helpers only.

## Tests

Python tests live under `tests/`:

```bash
pytest
```

Frontend tests live under `frontend/`:

```bash
cd frontend
npm test
```
