from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .database import Base, engine
from .domain import DOMAIN_CONFIG
from .routers import api, web

BASE_DIR = Path(__file__).resolve().parent.parent

app = FastAPI(
    title=DOMAIN_CONFIG.app_title,
    description=DOMAIN_CONFIG.app_subtitle,
    version="1.0.0",
)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


@app.get("/health", tags=["system"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(web.router)
app.include_router(api.router)
