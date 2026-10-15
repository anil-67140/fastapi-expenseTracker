"""Cross-cutting behaviour: error handlers, middleware, CORS, rate limiting, health, static files."""
import httpx
from httpx import ASGITransport, AsyncClient

from app.main import app
from tests.conftest import PASSWORD


async def test_health_and_static_landing_page(client):
    r = await client.get("/health")
    assert r.status_code == 200 and r.json()["database"] == "up"
    page = await client.get("/")
    assert page.status_code == 200 and "Expense Tracker API" in page.text
    assert (await client.get("/static/favicon.svg")).status_code == 200


async def test_unknown_route_uses_standard_error_shape(client):
    r = await client.get("/nope")
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found" and err["request_id"]


async def test_middleware_adds_request_id_timing_and_security_headers(client):
    r = await client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["x-request-id"] == "abc123"
    assert float(r.headers["x-process-time-ms"]) >= 0
    assert r.headers["x-content-type-options"] == "nosniff"


async def test_cors_preflight_allows_configured_origin_only(client):
    ok = await client.options(
        "/expenses",
        headers={"Origin": "http://localhost:5000", "Access-Control-Request-Method": "POST"},
    )
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5000"
    bad = await client.options(
        "/expenses",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers


async def test_login_is_rate_limited_with_retry_after(client):
    await client.post("/auth/register", json={"email": "r@example.com", "full_name": "R", "password": PASSWORD})
    statuses = []
    for _ in range(12):
        r = await client.post("/auth/token", data={"username": "r@example.com", "password": "wrong-wrong"})
        statuses.append(r.status_code)
    assert statuses[0] == 401 and 429 in statuses
    assert r.headers["retry-after"].isdigit()
    assert r.json()["error"]["code"] == "rate_limited"


async def test_rate_limit_headers_on_normal_calls(client, auth):
    r = await client.get("/users/me", headers=auth)
    assert int(r.headers["x-ratelimit-remaining"]) < int(r.headers["x-ratelimit-limit"])


async def test_unhandled_exception_returns_safe_500():
    async def boom():
        raise RuntimeError("secret internal detail")

    app.add_api_route("/__boom", boom, include_in_schema=False)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/__boom")
    assert r.status_code == 500
    assert r.json()["error"]["code"] == "internal_error"
    assert "secret" not in r.text
