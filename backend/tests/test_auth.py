from datetime import timedelta

import jwt

from app.config import settings
from app.security import create_access_token
from tests.conftest import PASSWORD, make_user


async def test_register_hides_password_hash(client):
    r = await client.post("/auth/register", json={"email": "A@Example.com", "full_name": "Ada", "password": PASSWORD})
    assert r.status_code == 201
    body = r.json()
    assert body["email"] == "a@example.com"  # normalised
    assert "password" not in body and "hashed_password" not in body


async def test_duplicate_email_returns_409(client):
    await make_user(client)
    r = await client.post("/auth/register", json={"email": "ada@example.com", "full_name": "X", "password": PASSWORD})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


async def test_weak_password_is_rejected_with_field_details(client):
    r = await client.post("/auth/register", json={"email": "b@example.com", "full_name": "B", "password": "short"})
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "validation_error"
    assert err["details"][0]["field"] == "password"


async def test_login_wrong_password_401(client):
    await make_user(client)
    r = await client.post("/auth/token", data={"username": "ada@example.com", "password": "nope-nope-nope"})
    assert r.status_code == 401
    assert r.headers["www-authenticate"] == "Bearer"


async def test_token_contains_subject_and_expiry(client):
    headers = await make_user(client)
    token = headers["Authorization"].split()[1]
    payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
    assert payload["sub"] == "1" and "exp" in payload


async def test_protected_route_requires_token(client):
    r = await client.get("/users/me")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "unauthorized"


async def test_expired_token_is_rejected(client):
    await make_user(client)
    token, _ = create_access_token("1", expires_delta=timedelta(seconds=-5))
    r = await client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert "expired" in r.json()["error"]["message"].lower()


async def test_tampered_token_is_rejected(client):
    r = await client.get("/users/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert r.status_code == 401


async def test_update_profile_budget(client, auth):
    r = await client.patch("/users/me", json={"monthly_budget": "2500.50", "currency": "PKR"}, headers=auth)
    assert r.status_code == 200
    assert r.json()["monthly_budget"] == 2500.5 and r.json()["currency"] == "PKR"
    r = await client.patch("/users/me", json={}, headers=auth)
    assert r.status_code == 400
