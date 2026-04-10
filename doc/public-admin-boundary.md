# HeyBlog Public/Admin Boundary

## Product Surfaces

### Public

Public surface is the user-facing discovery product:

- `/`
- `/stats`
- `/blogs`
- `/blogs/:blogId`
- `/search`
- `/graph`
- `/about`

Public capabilities:

- browse discovered blogs
- inspect blog detail and graph relationships
- search by blog/site/relation clues
- submit ingestion requests and check request status

### Admin

Admin surface is the protected operations console:

- `/admin`
- `/admin/control`
- `/admin/runtime/progress`
- `/admin/runtime/current`
- `/admin/blog-labeling`

Admin capabilities:

- crawler runtime control
- manual crawl/bootstrap triggers
- database maintenance
- dedup scans
- blog labeling

## API Boundary

### Public API

- `GET /api/status`
- `GET /api/blogs`
- `GET /api/blogs/catalog`
- `GET /api/blogs/{blog_id}`
- `GET /api/edges`
- `GET /api/graph*`
- `GET /api/stats`
- `GET /api/search`
- `POST /api/ingestion-requests`
- `GET /api/ingestion-requests/{request_id}`

### Admin API

- `GET /api/admin/runtime/status`
- `GET /api/admin/runtime/current`
- `POST /api/admin/runtime/start`
- `POST /api/admin/runtime/stop`
- `POST /api/admin/runtime/run-batch`
- `POST /api/admin/crawl/bootstrap`
- `POST /api/admin/crawl/run`
- `POST /api/admin/database/reset`
- `GET /api/admin/blog-labeling/candidates`
- `GET /api/admin/blog-labeling/tags`
- `POST /api/admin/blog-labeling/tags`
- `PUT /api/admin/blog-labeling/labels/{blog_id}`
- `POST /api/admin/blog-dedup-scans`
- `GET /api/admin/blog-dedup-scans/latest`
- `GET /api/admin/blog-dedup-scans/{run_id}`
- `GET /api/admin/blog-dedup-scans/{run_id}/items`

## Auth

- Admin API requires `Authorization: Bearer <HEYBLOG_ADMIN_TOKEN>` unless `HEYBLOG_ADMIN_DEV_BYPASS=true` is explicitly enabled.
- Missing token returns `401 admin_auth_required`.
- Invalid token returns `403 admin_auth_invalid`.
- Unconfigured admin auth returns `503 admin_auth_not_configured`.
