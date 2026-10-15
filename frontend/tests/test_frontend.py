"""Frontend tests run against a FakeApi, so no backend is needed."""
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api_client import ApiError  # noqa: E402
from app import create_app  # noqa: E402

EXPENSE = {
    "id": 1, "title": "Groceries", "amount": 42.5, "category": "food", "status": "pending",
    "expense_date": "2026-10-15", "notes": "weekly", "receipt_url": None,
    "created_at": "2026-10-15T10:00:00", "updated_at": "2026-10-15T10:00:00",
}


class FakeApi:
    expire = False
    created: list = []

    def __init__(self, token=None, client_ip=None):
        self.token = token
        self.client_ip = client_ip

    def login(self, email, password):
        if password != "good-password":
            raise ApiError(401, "Incorrect email or password.")
        return "fake-jwt"

    def me(self):
        return {"full_name": "Ada", "currency": "USD"}

    def _guard(self):
        if self.expire:
            raise ApiError(401, "Token has expired.")

    def list_expenses(self, params):
        self._guard()
        return {"items": [EXPENSE], "total": 1, "page": 1, "page_size": 10, "pages": 1, "has_next": False, "has_prev": False}

    def stats(self, month=None):
        return {"month": "2026-10", "currency": "USD", "expense_count": 1, "total_spent": 42.5, "paid_total": 0,
                "pending_total": 42.5, "monthly_budget": 1000, "budget_used_percent": 4.3, "over_budget": False,
                "by_category": [{"category": "food", "total": 42.5, "count": 1}]}

    def activity(self, limit=8):
        return [{"id": 1, "action": "created", "entity": "expense", "entity_id": 1, "created_at": "2026-10-15T10:00:00"}]

    def create_expense(self, data):
        FakeApi.created.append(data)
        return {**EXPENSE, **data}


@pytest.fixture
def client():
    FakeApi.expire = False
    FakeApi.created = []
    app = create_app(api_factory=lambda token=None, client_ip=None: FakeApi(token, client_ip))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def csrf_from(client, path="/login"):
    html = client.get(path).get_data(as_text=True)
    return re.search(r'name="_csrf" value="([^"]+)"', html).group(1)


def login(client):
    token = csrf_from(client)
    return client.post("/login", data={"email": "a@example.com", "password": "good-password", "_csrf": token})


def test_root_and_dashboard_redirect_to_login_when_anonymous(client):
    assert client.get("/").headers["Location"].endswith("/login")
    assert client.get("/dashboard").headers["Location"].endswith("/login")


def test_post_without_csrf_token_is_rejected(client):
    r = client.post("/login", data={"email": "a@example.com", "password": "good-password"})
    assert r.status_code == 400


def test_bad_login_shows_api_message(client):
    token = csrf_from(client)
    r = client.post("/login", data={"email": "a@example.com", "password": "nope", "_csrf": token})
    assert r.status_code == 401 and b"Incorrect email or password." in r.data


def test_login_then_dashboard_renders_server_side(client):
    assert login(client).status_code == 302
    html = client.get("/dashboard").get_data(as_text=True)
    assert "Groceries" in html and "$42.50" in html and "October 2026" in html
    assert "x-data" not in html and "alpinejs" not in html.lower()  # Alpine.js is gone


def test_create_expense_posts_form_to_api(client):
    login(client)
    token = csrf_from(client, "/dashboard")
    r = client.post("/expenses", data={"title": "Taxi", "amount": "12.00", "category": "transport", "_csrf": token})
    assert r.status_code == 302
    assert FakeApi.created[0]["title"] == "Taxi" and FakeApi.created[0]["category"] == "transport"


def test_expired_token_sends_user_back_to_login(client):
    login(client)
    FakeApi.expire = True
    r = client.get("/dashboard")
    assert r.status_code == 302 and r.headers["Location"].endswith("/login")
    assert client.get("/dashboard").status_code == 302  # session was cleared
