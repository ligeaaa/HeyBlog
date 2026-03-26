# HeyBlog

HeyBlog is an MVP crawler for the blog friend-link ecosystem. It starts from a set
of seed blog URLs, discovers friend-link pages, extracts outbound blog links,
stores the resulting graph in SQLite, and exposes read APIs for status, graph
data, and exports.

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
python -m uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`, with interactive docs at
`/docs`.

## Seed Blogs

The initial seed list in `seed.csv` contains:

- `https://blog.elykia.cn/`
- `https://www.qladgk.com/`
- `https://www.imaegoo.com/`

## Suggested Flow

1. Start the API server.
2. Call `POST /api/crawl/bootstrap` to import seeds.
3. Call `POST /api/crawl/run` to process pending blogs.
4. Use the read APIs to inspect status, nodes, edges, stats, and logs.
5. Read exported graph artifacts under `data/exports/`.

## Docker

```bash
docker compose up --build
```
