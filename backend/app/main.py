"""Application entry point: wires settings, middleware, routers, error handlers and static files."""
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from starlette.middleware.gzip import GZipMiddleware

from app import __version__
from app.config import settings
from app.database import engine, init_db
from app.dependencies import DbSession
from app.exceptions import register_exception_handlers
from app.middleware import RequestContextMiddleware, SecurityHeadersMiddleware
from app.routers import auth, crawler, expenses, external, stats, users
from app.schemas import HealthOut

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
UPLOAD_DIR = Path(settings.upload_dir)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

TAGS = [
    {"name": "Authentication", "description": "Register and obtain a JWT (OAuth2 password flow)."},
    {"name": "Users", "description": "Profile, budget and recent activity."},
    {"name": "Expenses", "description": "CRUD, filtering, pagination, receipts, CSV export."},
    {"name": "Statistics", "description": "Cached monthly totals and budget pressure."},
    {"name": "Third-party API", "description": "Live exchange rates from an external provider."},
    {"name": "Web crawling", "description": "Concurrent, SSRF-safe page previews."},
    {"name": "System", "description": "Health check."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown: create tables, open ONE shared HTTP client, close everything on exit."""
    await init_db()
    app.state.http_client = httpx.AsyncClient(timeout=httpx.Timeout(10.0), limits=httpx.Limits(max_connections=20))
    yield
    await app.state.http_client.aclose()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version=__version__,
    description="Learning project that showcases FastAPI best practices. Click **Authorize** after logging in.",
    openapi_tags=TAGS,
    lifespan=lifespan,
)

register_exception_handlers(app)

# Middleware order: the LAST one added is the OUTERMOST (runs first on the way in).
# CORS goes last so even error responses from inner layers get CORS headers.
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,  # explicit origins, never "*" together with credentials
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining", "X-Cache", "Retry-After"],
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(expenses.router)
app.include_router(stats.router)
app.include_router(external.router)
app.include_router(crawler.router)

# Static files: the API's own assets, plus uploaded receipts (random, unguessable file names).
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")


@app.get("/", include_in_schema=False)
async def root() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", response_model=HealthOut, tags=["System"], summary="Liveness + database check")
async def health(db: DbSession):
    try:
        await db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"status": "degraded", "database": "down", "version": __version__, "environment": settings.environment},
        )
    return HealthOut(status="ok", database="up", version=__version__, environment=settings.environment)
