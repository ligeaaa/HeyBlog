# HeyBlog

HeyBlog is a split-service MVP for crawling the blog friend-link ecosystem. It starts
from `seed.csv`, discovers friend-link pages, extracts outbound blog links, stores the
resulting graph in SQLite or PostgreSQL, and serves a browser panel plus public API on
top of `frontend` + `backend` + `crawler` + `search` + `persistence-api`.

## Runtime Model

The real implementation lives in the top-level service packages:

- `frontend/`
- `backend/`
- `crawler/`
- `search/`
- `persistence_api/`
- `shared/`

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

Use this when you are changing `frontend/src/` and want the panel plus the real backend
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

## Suggested Flow

1. Import seeds with `POST /api/crawl/bootstrap`.
2. Process pending blogs with `POST /api/crawl/run` or runtime batch controls.
3. Inspect status, blogs, graph, search, and logs through the public `/api/*` surface.
4. Read exported graph artifacts under `data/exports/` or `volumes/exports/`.

## Documentation Map

- [Project structure](doc/project-structure.md): directories, source-of-truth packages, and entrypoints
- [Services overview](doc/services-overview.md): service responsibilities, dependencies, and edit boundaries
- [Service architecture](doc/service-architecture.md): runtime call chains and data ownership
- [API docs](doc/api-docs.md): public and internal HTTP contracts
- [Config reference](doc/config-reference.md): environment variables, defaults, and service consumers
- [Developer workflows](doc/developer-workflows.md): where to start for common tasks
- [Graph/community PRD](doc/prd-graph-community-discovery.md): future product direction for graph analysis and community discovery

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
