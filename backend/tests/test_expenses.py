from datetime import date

from tests.conftest import make_user

NEW = {"title": "Groceries", "amount": "42.50", "category": "food"}


async def create(client, auth, **overrides):
    r = await client.post("/expenses", json={**NEW, **overrides}, headers=auth)
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_returns_201_location_and_number_amount(client, auth):
    r = await client.post("/expenses", json=NEW, headers=auth)
    assert r.status_code == 201
    assert r.headers["location"] == f"/expenses/{r.json()['id']}"
    assert r.json()["amount"] == 42.5  # Decimal in, JSON number out
    assert r.json()["status"] == "pending"


async def test_validation_rejects_bad_amount_and_category(client, auth):
    r = await client.post("/expenses", json={**NEW, "amount": "-5"}, headers=auth)
    assert r.status_code == 422
    r = await client.post("/expenses", json={**NEW, "category": "yachts"}, headers=auth)
    assert r.status_code == 422


async def test_get_update_toggle_delete_flow(client, auth):
    e = await create(client, auth)
    url = f"/expenses/{e['id']}"
    assert (await client.get(url, headers=auth)).json()["title"] == "Groceries"

    r = await client.patch(url, json={"title": "Weekly groceries", "amount": "50"}, headers=auth)
    assert r.status_code == 200 and r.json()["title"] == "Weekly groceries" and r.json()["amount"] == 50

    r = await client.patch(url + "/toggle", headers=auth)
    assert r.json()["status"] == "paid"
    r = await client.patch(url + "/toggle", headers=auth)
    assert r.json()["status"] == "pending"

    r = await client.delete(url, headers=auth)
    assert r.status_code == 204 and r.content == b""
    assert (await client.get(url, headers=auth)).status_code == 404


async def test_patch_rejects_null_for_required_field_and_empty_body(client, auth):
    e = await create(client, auth)
    assert (await client.patch(f"/expenses/{e['id']}", json={"title": None}, headers=auth)).status_code == 422
    assert (await client.patch(f"/expenses/{e['id']}", json={}, headers=auth)).status_code == 400


async def test_users_cannot_see_each_others_expenses(client, auth):
    e = await create(client, auth)
    other = await make_user(client, "grace@example.com")
    assert (await client.get(f"/expenses/{e['id']}", headers=other)).status_code == 404
    assert (await client.delete(f"/expenses/{e['id']}", headers=other)).status_code == 404
    assert (await client.get("/expenses", headers=other)).json()["total"] == 0


async def test_pagination_metadata(client, auth):
    for i in range(25):
        await create(client, auth, title=f"Item {i}", amount=str(i + 1))
    r = await client.get("/expenses", params={"page": 2, "page_size": 10}, headers=auth)
    body = r.json()
    assert body["total"] == 25 and body["pages"] == 3 and len(body["items"]) == 10
    assert body["has_next"] and body["has_prev"]
    last = (await client.get("/expenses", params={"page": 3, "page_size": 10}, headers=auth)).json()
    assert len(last["items"]) == 5 and not last["has_next"]
    assert (await client.get("/expenses", params={"page_size": 500}, headers=auth)).status_code == 422


async def test_filters_search_and_sorting(client, auth):
    await create(client, auth, title="Bus pass", amount="30", category="transport", status="paid")
    await create(client, auth, title="Pizza night", amount="20", category="food")
    await create(client, auth, title="Rent", amount="900", category="housing", notes="March rent")

    def titles(r):
        return [i["title"] for i in r.json()["items"]]

    assert titles(await client.get("/expenses", params={"category": "food"}, headers=auth)) == ["Pizza night"]
    assert titles(await client.get("/expenses", params={"status": "paid"}, headers=auth)) == ["Bus pass"]
    assert titles(await client.get("/expenses", params={"q": "RENT"}, headers=auth)) == ["Rent"]
    assert titles(await client.get("/expenses", params={"min_amount": 25}, headers=auth)) == ["Rent", "Bus pass"]
    assert titles(await client.get("/expenses", params={"sort": "amount_desc"}, headers=auth)) == ["Rent", "Bus pass", "Pizza night"]
    assert titles(await client.get("/expenses", params={"sort": "amount_asc"}, headers=auth)) == ["Pizza night", "Bus pass", "Rent"]
    r = await client.get("/expenses", params={"date_from": "2030-01-02", "date_to": "2030-01-01"}, headers=auth)
    assert r.status_code == 400


async def test_csv_export_and_formula_injection_guard(client, auth):
    await create(client, auth, title="=HYPERLINK(\"http://evil\")", amount="1")
    r = await client.get("/expenses/export/csv", headers=auth)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    assert "'=HYPERLINK" in r.text


async def test_background_task_writes_activity(client, auth):
    e = await create(client, auth)
    await client.patch(f"/expenses/{e['id']}/toggle", headers=auth)
    actions = [a["action"] for a in (await client.get("/users/me/activity", headers=auth)).json()]
    assert "created" in actions and "marked paid" in actions


async def test_stats_totals_cache_and_invalidation(client, auth):
    today = date.today().isoformat()
    await create(client, auth, title="A", amount="100", category="food", status="paid", expense_date=today)
    e = await create(client, auth, title="B", amount="50", category="housing", expense_date=today)
    await client.patch("/users/me", json={"monthly_budget": "100"}, headers=auth)

    first = await client.get("/stats", headers=auth)
    assert first.headers["x-cache"] == "MISS"
    s = first.json()
    assert s["total_spent"] == 150 and s["paid_total"] == 100 and s["pending_total"] == 50
    assert s["over_budget"] is True and s["budget_used_percent"] == 150.0
    assert s["by_category"][0]["category"] == "food"

    assert (await client.get("/stats", headers=auth)).headers["x-cache"] == "HIT"
    await client.patch(f"/expenses/{e['id']}/toggle", headers=auth)  # a write invalidates the cache
    again = await client.get("/stats", headers=auth)
    assert again.headers["x-cache"] == "MISS" and again.json()["pending_total"] == 0


async def test_stats_rejects_bad_month(client, auth):
    assert (await client.get("/stats", params={"month": "2026-13"}, headers=auth)).status_code == 422
