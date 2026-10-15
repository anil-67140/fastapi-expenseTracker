"""Shared fixtures.

Environment variables are set BEFORE the app is imported, so the app uses a
throw-away SQLite file and upload folder instead of your real data.
"""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="expense-tests-")
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{_tmp}/test.db"
os.environ["UPLOAD_DIR"] = f"{_tmp}/uploads"
os.environ["SECRET_KEY"] = "test-secret-key-test-secret-key-0123456789"
os.environ["ENVIRONMENT"] = "testing"

import httpx  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.cache import cache  # noqa: E402
from app.database import Base, engine  # noqa: E402
from app.dependencies import get_http_client  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import reset_rate_limits  # noqa: E402

PASSWORD = "correct-horse-battery"


@pytest_asyncio.fixture(autouse=True)
async def clean_state():
    """Fresh tables, empty cache and rate-limit counters for every test."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    cache.clear()
    reset_rate_limits()
    yield
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest_asyncio.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


async def make_user(client: AsyncClient, email: str = "ada@example.com") -> dict[str, str]:
    """Register + log in. Returns Authorization headers."""
    r = await client.post("/auth/register", json={"email": email, "full_name": "Ada", "password": PASSWORD})
    assert r.status_code == 201, r.text
    r = await client.post("/auth/token", data={"username": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest_asyncio.fixture
async def auth(client):
    return await make_user(client)


def override_http(handler):
    """Replace the shared HTTP client with one that answers from `handler` (no real network)."""
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.dependency_overrides[get_http_client] = lambda: mock_client
    return mock_client
