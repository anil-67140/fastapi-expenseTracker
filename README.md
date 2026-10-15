# 💸 Expense Tracker: FastAPI + Flask

> A full-stack expense tracker built to show real command of **FastAPI** (JSON API) and **Flask** (server-rendered UI). Track spending, payment status and budget pressure, with auth, uploads, caching, rate limiting, tests and a one-file Render deploy.

![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-API-009688?style=for-the-badge&logo=fastapi&logoColor=white)
![Flask](https://img.shields.io/badge/Flask-Web_UI-000000?style=for-the-badge&logo=flask&logoColor=white)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-2.0_async-D71F00?style=for-the-badge&logo=sqlalchemy&logoColor=white)
![Pytest](https://img.shields.io/badge/Tests-pytest-0A9EDC?style=for-the-badge&logo=pytest&logoColor=white)
![Render](https://img.shields.io/badge/Render-Deploy-46E3B7?style=for-the-badge&logo=render&logoColor=0B0F19)

Alpine.js is gone. The UI is now **Flask + Jinja templates**: every action is a normal HTML form (`POST → redirect → GET`), so there is no client-side framework to explain, and the browser never talks to the database. Flask calls the FastAPI backend, just like any other API client.

---

## Architecture

```
┌─────────┐   HTML + forms    ┌──────────────────┐   JSON + Bearer JWT   ┌──────────────────────┐
│ Browser │ ────────────────▶ │  Flask frontend  │ ────────────────────▶ │   FastAPI backend    │
└─────────┘ ◀──────────────── │  (Jinja, session)│ ◀──────────────────── │ routers · services   │
                              └──────────────────┘                       │ SQLAlchemy (async)   │
                               stores the JWT in a                       └───┬──────────┬───────┘
                               signed session cookie                         │          │
                                                                  SQLite/Postgres   uploads/  ──▶ exchange-rate API,
                                                                                                  crawled web pages
```

Request path for adding an expense: browser form → Flask (CSRF check) → `POST /expenses` with the JWT → rate limiter → auth dependency → Pydantic validation → DB commit → cache invalidation → background audit log → `201 Created`.

---

## Topic coverage: where to find each one

| # | Topic | Where | What it demonstrates |
|---|-------|-------|----------------------|
| 1 | **Response models & hiding sensitive data** | `backend/app/schemas.py`, `routers/auth.py` | `UserOut` has no password hash; `ExpenseOut` hides the internal `receipt_filename` and exposes a computed `receipt_url`; `Money` type turns `Decimal` into JSON numbers |
| 2 | **Status codes & custom responses** | `routers/expenses.py` | `201` + `Location` header on create, `204` on delete, `409` on duplicates, `StreamingResponse` for CSV, `FileResponse` for the landing page; error codes documented via `responses=` in `/docs` |
| 3 | **Exception handling & global handlers** | `backend/app/exceptions.py` | Custom `AppError` hierarchy + handlers for validation, HTTP, DB and unexpected errors, all returning one JSON shape with a `request_id`; internals are never leaked |
| 4 | **Dependency injection** | `backend/app/dependencies.py` | `DbSession`, `CurrentUser`, `OwnedExpense`, `Filters`, `Pagination`, `HttpClient`, built from small composable dependencies; tests swap them via `dependency_overrides` |
| 5 | **Middleware** | `backend/app/middleware.py`, `main.py` | Request-ID + timing + logging, security headers, GZip, CORS, and why add-order matters |
| 6 | **DB integration & SQLAlchemy ORM** | `backend/app/database.py`, `models.py` | SQLAlchemy 2.0 typed `Mapped[]` models, relationships, indexes, `Numeric` money, `lazy="raise"` to avoid async lazy-load traps |
| 7 | **CRUD API with a database** | `routers/expenses.py` | Create / read / list / `PATCH` (only sent fields) / toggle / delete, with per-user ownership checks |
| 8 | **Async programming** | everywhere | Async engine + session, `httpx.AsyncClient`, `asyncio.gather` + `Semaphore` in the crawler, `asyncio.to_thread` for file writes and HTML parsing |
| 9 | **Authentication & JWT** | `backend/app/security.py` | Signed, expiring tokens (`sub`, `iat`, `exp`), expired/tampered token handling |
| 10 | **OAuth2 with JWT & password hashing** | `routers/auth.py`, `dependencies.py` | `OAuth2PasswordBearer` + `OAuth2PasswordRequestForm` (the *Authorize* button in `/docs` works), Argon2 hashing, a dummy hash check for unknown emails so response time doesn't reveal which accounts exist |
| 11 | **File uploading & static files** | `services/storage.py`, `main.py` | Type allow-list, **magic-byte sniffing**, chunked size limit, random file names, `StaticFiles` mounts for `/static` and `/uploads` |
| 12 | **CORS** | `main.py`, `tests/test_platform.py` | Explicit allowed origins (never `*` with credentials); tested with real preflight requests |
| 13 | **Environment variables** | `backend/app/config.py`, `.env.example` | `pydantic-settings`, typed config, `postgres://` URL normalisation, **app refuses to start in production with the default secret** |
| 14 | **API testing with pytest** | `backend/tests/`, `frontend/tests/` | 37 backend + 6 frontend tests: isolated temp DB per test, auth flows, pagination, uploads, rate limits, cache, mocked third-party calls |
| 15 | **Third-party API integration** | `services/exchange.py`, `routers/external.py` | Shared async client, timeouts, upstream failures mapped to `502`, response caching |
| 16 | **Web crawling with FastAPI** | `services/crawler.py`, `routers/crawler.py` | Concurrent fetching, BeautifulSoup extraction, partial-failure handling, **SSRF protection** (see below) |
| 17 | **Pagination** | `backend/app/pagination.py` | `page` / `page_size` dependency, generic `Page[T]` response with `total`, `pages`, `has_next`, `has_prev` |
| 18 | **Caching** | `backend/app/cache.py`, `routers/stats.py` | TTL cache, `X-Cache: HIT/MISS` header, invalidation on every write |
| 19 | **API rate limiting** | `backend/app/rate_limit.py` | Sliding window as a dependency, `429` + `Retry-After` + `X-RateLimit-*` headers, stricter limit on login |
| 20 | **Deploying to Render** | `render.yaml` | Blueprint that deploys both services with generated secrets and a health check |

### Extras beyond your list (good interview material)

- **Background tasks**: audit-log entries are written *after* the response is sent (`services/audit.py`).
- **Lifespan events**: tables and the shared HTTP client are created at startup and closed at shutdown.
- **Streaming CSV export** with spreadsheet formula-injection protection.
- **SSRF defence** in the crawler: it resolves DNS, rejects private/loopback/link-local addresses (incl. cloud metadata IPs) and re-checks every redirect.
- **CSRF protection** in Flask (per-session token on every POST) and session-fixation protection on login.
- **Health check** that verifies the database, **CI** on GitHub Actions, and `/docs` with documented error responses.

---

## Quick start (local)

You need Python 3.12+. Use **two terminals**.

**1. Backend (FastAPI), port 8000**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env               # Windows: copy .env.example .env
uvicorn app.main:app --reload
```

- Interactive docs: <http://127.0.0.1:8000/docs>
- Health check: <http://127.0.0.1:8000/health>

**2. Frontend (Flask), port 5000**

```bash
cd frontend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
python app.py
```

Open <http://127.0.0.1:5000>, create an account and start adding expenses.

> Prefer `uv`? `uv venv && uv pip install -r requirements-dev.txt` works the same way.

### Run the tests

```bash
cd backend  && pytest      # 37 tests, uses a throw-away database
cd frontend && pytest      # 6 tests, uses a fake API, no server needed
```

---

## Configuration

**Backend** (`backend/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `ENVIRONMENT` | `development` | Set `production` to enforce a real secret |
| `SECRET_KEY` | dev placeholder | Signs JWTs. **Required in production** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | JWT lifetime |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/expenses.db` | Any SQLAlchemy async URL; Postgres URLs are auto-converted |
| `CORS_ORIGINS` | `http://localhost:5000,...` | Comma-separated browser origins |
| `UPLOAD_DIR` / `MAX_UPLOAD_MB` | `uploads` / `5` | Receipt storage |
| `CACHE_TTL_SECONDS` | `30` | Stats cache lifetime |
| `RATE_LIMIT_PER_MINUTE` | `120` | General limit per client |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | Login/register limit per client |
| `CRAWLER_RATE_LIMIT_PER_MINUTE` | `10` | Crawler limit per client |

**Frontend** (`frontend/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `API_URL` | `http://127.0.0.1:8000` | Where Flask calls the API |
| `API_PUBLIC_URL` | same as `API_URL` | Where the *browser* loads receipts and docs from (set only if it differs) |
| `SECRET_KEY` | dev placeholder | Signs the session cookie. **Required in production** |
| `ENVIRONMENT` | `development` | `production` turns on secure cookies and proxy handling |

---

## API overview

Everything except register/login/health needs `Authorization: Bearer <token>`. Full details are in `/docs`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/register` | Create account → `201` |
| `POST` | `/auth/token` | Log in (form: `username`=email, `password`) → JWT |
| `GET` / `PATCH` | `/users/me` | Profile; update name, monthly budget, currency |
| `GET` | `/users/me/activity` | Recent actions (written by background tasks) |
| `POST` | `/expenses` | Create → `201` + `Location` |
| `GET` | `/expenses` | List with `q`, `category`, `status`, `min_amount`, `max_amount`, `date_from`, `date_to`, `sort`, `page`, `page_size` |
| `GET` / `PATCH` / `DELETE` | `/expenses/{id}` | Read / partial update / delete → `204` |
| `PATCH` | `/expenses/{id}/toggle` | Flip pending ↔ paid |
| `POST` | `/expenses/{id}/receipt` | Upload jpg/png/webp/pdf |
| `GET` | `/expenses/export/csv` | Streamed CSV download |
| `GET` | `/stats?month=YYYY-MM` | Totals, category breakdown, budget pressure (cached) |
| `GET` | `/external/rates`, `/external/convert` | Live exchange rates (third-party API) |
| `POST` | `/crawler/preview` | Crawl up to 5 URLs concurrently |
| `GET` | `/health` | Liveness + DB check |
| `GET` | `/uploads/{file}`, `/static/...` | Served static files |

All errors share one shape:

```json
{ "error": { "code": "validation_error", "message": "Request validation failed.",
             "details": [{"field": "amount", "message": "Input should be greater than 0", "type": "greater_than"}],
             "request_id": "3f2a…" } }
```

> **Upgrading from the old version?** The old `/api/items` endpoints are now `/expenses`, and there is auth: each user only sees their own data.

---

## Deploy on Render

`render.yaml` defines **two web services**: `expense-tracker-api` (FastAPI) and `expense-tracker-web` (Flask).

1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, pick the repo.
3. Render prompts for the values marked `sync: false`:
   - `API_URL` (web service): public URL of the API, e.g. `https://expense-tracker-api.onrender.com`
   - `CORS_ORIGINS` (API service): public URL of the Flask app, e.g. `https://expense-tracker-web.onrender.com`
4. `SECRET_KEY` is generated for you on both services.
5. After the first deploy, check the real service URLs in the dashboard (Render may add a suffix if a name is taken) and correct the two variables if needed.

Things to know about the free tier (check Render's current terms):

- Free web services spin down when idle, so the **first request after a pause can take a while**. The Flask client allows 30 s and shows a friendly message if the API is still waking.
- **SQLite and uploaded receipts live on temporary disk and reset on each deploy.** For persistence, set `DATABASE_URL` to a Postgres database (the `asyncpg` driver is already included) and move receipts to object storage (S3 / R2).

---

## Project structure

```
.
├── backend/                     # FastAPI service
│   ├── app/
│   │   ├── main.py              # app wiring: lifespan, middleware, routers, static mounts
│   │   ├── config.py            # env vars → typed Settings
│   │   ├── database.py          # async engine, session, get_db
│   │   ├── models.py            # User, Expense, AuditLog
│   │   ├── schemas.py           # request/response models, Page[T], error models
│   │   ├── security.py          # Argon2 hashing, JWT create/verify
│   │   ├── dependencies.py      # CurrentUser, OwnedExpense, Filters, HttpClient …
│   │   ├── exceptions.py        # AppError types + global handlers
│   │   ├── middleware.py        # request id/timing, security headers
│   │   ├── cache.py             # TTL cache
│   │   ├── rate_limit.py        # sliding-window limiter dependency
│   │   ├── pagination.py        # PaginationParams + paginate()
│   │   ├── routers/             # auth, users, expenses, stats, external, crawler
│   │   └── services/            # storage, exchange, crawler, audit
│   ├── static/                  # landing page + favicon (served at /static)
│   ├── tests/                   # pytest suite
│   └── requirements*.txt
├── frontend/                    # Flask service
│   ├── app.py                   # routes, CSRF, filters, error handling
│   ├── api_client.py            # the only place that talks to the API
│   ├── templates/               # Jinja: dashboard, edit, tools, auth, error
│   ├── static/css/style.css
│   ├── tests/
│   └── requirements*.txt
├── render.yaml                  # Render Blueprint (both services)
└── .github/workflows/ci.yml     # runs both test suites on every push
```

---

## Design decisions & interview talking points

- **Why Flask calls the API instead of the DB:** one source of truth and business rules. The same API could serve a mobile app. Flask holds the JWT in a signed, `HttpOnly` session cookie.
- **Why async SQLAlchemy:** no thread blocking while waiting on I/O. Trade-off: no implicit lazy loading, so relationships are `lazy="raise"` and queries are explicit.
- **Why `Decimal` for money:** floats can't represent `0.1` exactly. Amounts are validated and summed as `Decimal`, then serialised as JSON numbers for clients.
- **Why 404 (not 403) for someone else's expense:** it doesn't confirm that the ID exists.
- **Why a custom error envelope:** clients parse one format; `request_id` ties an error to a log line.
- **Why validate file *content*:** the `Content-Type` header is client-controlled, so uploads are checked against magic bytes, size-limited while streaming, and stored under random names.
- **Middleware order:** the last `add_middleware` call is the outermost layer. CORS is added last so even error responses carry CORS headers.
- **Rate limiter and the Flask hop:** all browser traffic reaches the API from Flask's single IP, so Flask forwards the visitor's IP in `X-Forwarded-For`, and uvicorn runs with `--proxy-headers`. On Render the trusted-proxy setting is `*`, which means a direct API caller could spoof that header; per-user or per-API-key limits would close that gap.

### Known limitations and sensible next steps

- Cache and rate-limit state are **in process memory**: fine for one worker, but multiple instances need **Redis**.
- Tables are created at startup; a real project would use **Alembic** migrations.
- Receipts are served from unguessable URLs, but they are public to anyone with the link. Private storage with signed URLs would be stricter.
- No refresh tokens or token revocation yet; tokens just expire (default 60 min).
- The crawler checks DNS before connecting; pinning the resolved IP in a custom transport would also close the DNS-rebinding window. It does not read `robots.txt`.
- Not yet covered: WebSockets, OpenAPI client generation, structured JSON logging, Docker.
