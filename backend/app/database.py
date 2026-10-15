"""Async SQLAlchemy 2.0 engine, session factory and the `get_db` dependency."""
import warnings
from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import make_url
from sqlalchemy.exc import SAWarning
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# SQLite stores Numeric as float; we still use Decimal in Python for correct money maths.
warnings.filterwarnings("ignore", message=".*does not support Decimal.*", category=SAWarning)


def _ensure_sqlite_dir(url: str) -> None:
    parsed = make_url(url)
    if parsed.drivername.startswith("sqlite") and parsed.database and parsed.database != ":memory:":
        Path(parsed.database).parent.mkdir(parents=True, exist_ok=True)


_ensure_sqlite_dir(settings.database_url)

engine = create_async_engine(settings.database_url, echo=settings.debug, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)  # keep attributes after commit


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncIterator[AsyncSession]:
    """Dependency: one session per request, always closed, rolled back on error."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def init_db() -> None:
    """Create tables. (For real projects you would use Alembic migrations instead.)"""
    from app import models  # noqa: F401  (register models on Base.metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
