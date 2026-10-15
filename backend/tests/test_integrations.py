"""Third-party API + crawler, with all network traffic faked via httpx.MockTransport."""
import httpx

from app.services import crawler
from tests.conftest import override_http

RATES = {
    "result": "success",
    "time_last_update_utc": "Mon, 01 Jan 2026 00:00:01 +0000",
    "rates": {"USD": 1, "EUR": 0.9, "PKR": 280.0},
}


async def test_rates_are_fetched_then_served_from_cache(client, auth):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=RATES)

    override_http(handler)
    first = await client.get("/external/rates", params={"base": "usd", "symbols": "EUR,PKR"}, headers=auth)
    assert first.status_code == 200
    assert first.json()["rates"] == {"EUR": 0.9, "PKR": 280.0} and first.json()["cached"] is False
    second = await client.get("/external/rates", params={"base": "USD"}, headers=auth)
    assert second.json()["cached"] is True and second.headers["x-cache"] == "HIT"
    assert len(calls) == 1  # second request never hit the provider


async def test_convert(client, auth):
    override_http(lambda req: httpx.Response(200, json=RATES))
    r = await client.get("/external/convert", params={"amount": 10, "from": "USD", "to": "PKR"}, headers=auth)
    assert r.status_code == 200 and r.json()["converted"] == 2800.0
    bad = await client.get("/external/convert", params={"amount": 10, "from": "USD", "to": "ZZZ"}, headers=auth)
    assert bad.status_code == 400


async def test_upstream_failure_becomes_502_and_timeout_is_handled(client, auth):
    override_http(lambda req: httpx.Response(500))
    assert (await client.get("/external/rates", headers=auth)).status_code == 502

    def timeout(request):
        raise httpx.ConnectTimeout("slow", request=request)

    override_http(timeout)
    r = await client.get("/external/rates", params={"base": "EUR"}, headers=auth)
    assert r.status_code == 502 and "timed out" in r.json()["error"]["message"]


async def test_external_requires_auth(client):
    assert (await client.get("/external/rates")).status_code == 401


HTML = """<html><head><title>Cool Lamp</title>
<meta name="description" content="A very cool lamp"></head>
<body><h1>Cool Lamp</h1><h2>Details</h2><a href="/a">a</a><a href="/b">b</a>
<p>Only $1,299.99 today or 40.00 EUR</p></body></html>"""


async def test_crawler_extracts_data_and_isolates_failures(client, auth, monkeypatch):
    async def allow_all(url):  # skip real DNS in tests
        return None

    monkeypatch.setattr(crawler, "assert_public_url", allow_all)

    def handler(request: httpx.Request) -> httpx.Response:
        if "bad" in request.url.host:
            return httpx.Response(200, text="{}", headers={"content-type": "application/json"})
        return httpx.Response(200, text=HTML, headers={"content-type": "text/html; charset=utf-8"})

    override_http(handler)
    r = await client.post("/crawler/preview", json={"urls": ["https://shop.test/lamp", "https://bad.test/x"]}, headers=auth)
    assert r.status_code == 200
    good, bad = r.json()
    assert good["ok"] and good["title"] == "Cool Lamp" and good["description"] == "A very cool lamp"
    assert good["headings"] == ["Cool Lamp", "Details"] and good["link_count"] == 2
    assert "$1,299.99" in good["price_hints"]
    assert bad["ok"] is False and "HTML" in bad["error"]  # one bad URL did not fail the batch


async def test_crawler_blocks_private_addresses_ssrf(client, auth):
    override_http(lambda req: httpx.Response(200, text=HTML, headers={"content-type": "text/html"}))
    urls = ["http://127.0.0.1:8000/health", "http://169.254.169.254/latest/meta-data/", "http://localhost/"]
    r = await client.post("/crawler/preview", json={"urls": urls}, headers=auth)
    assert r.status_code == 200
    assert all(not item["ok"] and "private" in item["error"].lower() for item in r.json()[:2])


async def test_crawler_validates_input(client, auth):
    override_http(lambda req: httpx.Response(200))  # lifespan isn't run by ASGITransport
    assert (await client.post("/crawler/preview", json={"urls": []}, headers=auth)).status_code == 422
    assert (await client.post("/crawler/preview", json={"urls": ["not a url"]}, headers=auth)).status_code == 422
    too_many = [f"https://e{i}.com" for i in range(6)]
    assert (await client.post("/crawler/preview", json={"urls": too_many}, headers=auth)).status_code == 422
