"""Thin client the Flask app uses to talk to the FastAPI backend.

Flask never touches the database. It only calls the public REST API, exactly
like a mobile app or another service would.
"""
from typing import Any

import httpx

# One shared client = connection pooling across requests (httpx.Client is thread-safe).
_http = httpx.Client(timeout=httpx.Timeout(30.0, connect=10.0))


class ApiError(Exception):
    def __init__(self, status_code: int, message: str, details: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.details = details


def _error_from_response(resp: httpx.Response) -> ApiError:
    """Turn the API's standard error envelope into one readable message."""
    try:
        err = resp.json()["error"]
    except (ValueError, KeyError, TypeError):
        return ApiError(resp.status_code, f"Unexpected response from the API (HTTP {resp.status_code}).")
    message = err.get("message") or "Request failed."
    details = err.get("details")
    if isinstance(details, list) and details:
        message = "; ".join(f"{d.get('field', 'field')}: {d.get('message', '')}" for d in details)
    return ApiError(resp.status_code, message, details)


class ApiClient:
    def __init__(self, base_url: str, token: str | None = None, client_ip: str | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.client_ip = client_ip  # the END USER's IP, so the API rate-limits users, not our Flask server

    def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        if self.client_ip:
            headers["X-Forwarded-For"] = self.client_ip
        try:
            resp = _http.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        except httpx.TimeoutException:
            raise ApiError(504, "The API took too long to respond. On a free host it may be waking up; try again in a few seconds.") from None
        except httpx.HTTPError:
            raise ApiError(503, "Cannot reach the API. Is the backend running and API_URL correct?") from None
        if resp.status_code >= 400:
            raise _error_from_response(resp)
        return resp

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        return self._request(method, path, **kwargs).json()

    # --- auth / profile
    def register(self, email: str, full_name: str, password: str) -> dict:
        return self._json("POST", "/auth/register", json={"email": email, "full_name": full_name, "password": password})

    def login(self, email: str, password: str) -> str:
        return self._json("POST", "/auth/token", data={"username": email, "password": password})["access_token"]

    def me(self) -> dict:
        return self._json("GET", "/users/me")

    def update_me(self, **fields: Any) -> dict:
        return self._json("PATCH", "/users/me", json=fields)

    def activity(self, limit: int = 8) -> list[dict]:
        return self._json("GET", "/users/me/activity", params={"limit": limit})

    # --- expenses
    def list_expenses(self, params: dict) -> dict:
        return self._json("GET", "/expenses", params=params)

    def get_expense(self, expense_id: int) -> dict:
        return self._json("GET", f"/expenses/{expense_id}")

    def create_expense(self, data: dict) -> dict:
        return self._json("POST", "/expenses", json=data)

    def update_expense(self, expense_id: int, data: dict) -> dict:
        return self._json("PATCH", f"/expenses/{expense_id}", json=data)

    def toggle_expense(self, expense_id: int) -> dict:
        return self._json("PATCH", f"/expenses/{expense_id}/toggle")

    def delete_expense(self, expense_id: int) -> None:
        self._request("DELETE", f"/expenses/{expense_id}")

    def upload_receipt(self, expense_id: int, filename: str, content: bytes, content_type: str) -> dict:
        return self._json("POST", f"/expenses/{expense_id}/receipt", files={"file": (filename, content, content_type)})

    def export_csv(self) -> bytes:
        return self._request("GET", "/expenses/export/csv").content

    # --- stats / integrations
    def stats(self, month: str | None = None) -> dict:
        return self._json("GET", "/stats", params={"month": month} if month else None)

    def rates(self, base: str, symbols: str) -> dict:
        return self._json("GET", "/external/rates", params={"base": base, "symbols": symbols})

    def convert(self, amount: str, from_currency: str, to_currency: str) -> dict:
        return self._json("GET", "/external/convert", params={"amount": amount, "from": from_currency, "to": to_currency})

    def crawl(self, urls: list[str]) -> list[dict]:
        return self._json("POST", "/crawler/preview", json={"urls": urls})
