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
- submit user seed blog URLs for crawling
- register, log in, verify email, reset password, and save personal label selections

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
- blog labeling
- user list and simple role management

## API Boundary

### Public API

- `GET /api/status`
- `GET /api/blogs/catalog`
- `GET /api/blogs/lookup`
- `GET /api/blogs/{blog_id}`
- `GET /api/graph/views/core`
- `GET /api/graph/nodes/{blog_id}/neighbors`
- `GET /api/graph/snapshots/latest`
- `GET /api/graph/snapshots/{version}`
- `GET /api/stats`
- `POST /api/blogs/user-seeds`
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/me`
- `POST /api/auth/logout`
- `POST /api/auth/email/verify/request`
- `POST /api/auth/email/verify/confirm`
- `POST /api/auth/password/forgot`
- `POST /api/auth/password/reset`

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
- `GET /api/admin/hourly-stats`
- `GET /api/admin/users`
- `PATCH /api/admin/users/{user_id}/role`

## Auth

- HeyBlog has three identities: guest, regular user, and admin.
- Guest is any request without a valid user session.
- Regular users are stored with `role=user`.
- Admin users are stored with `role=admin` and must have a verified email to access admin APIs.
- Admin API accepts either `Authorization: Bearer <HEYBLOG_ADMIN_TOKEN>` as a migration/bootstrap fallback, or an admin user session token.
- Missing token returns `401 admin_auth_required`.
- Invalid token returns `403 admin_auth_invalid`.
- Non-admin or unverified user tokens return `403 admin_auth_forbidden`.
- Unconfigured legacy admin auth with no valid admin user session returns `503 admin_auth_not_configured`.
