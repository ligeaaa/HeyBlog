# app/ Retirement Plan

`app/` is retained only as a compatibility layer during directory decoupling.

Retirement gates:

1. No new implementation code lands under `app/`
2. Runtime entrypoints use top-level packages:
   - `backend/`
   - `crawler/`
   - `search/`
   - `persistence_api/`
   - `frontend/`
3. Tests prefer top-level package imports instead of `app/*`
4. `app/services/*`, `app/crawler/*`, `app/db/*`, and `app/clients/*` are shims only
5. Docker and docs no longer reference `app.main` or other `app/*` implementation paths

Deletion order:

1. `app/services/*`
2. `app/crawler/*`
3. `app/db/*`
4. `app/clients/*`
5. `app/config.py` / `app/state.py`
6. `app/main.py`
