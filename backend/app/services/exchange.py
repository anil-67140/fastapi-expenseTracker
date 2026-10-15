"""Third-party API integration: live currency rates from open.er-api.com (free, no key).

Patterns shown: shared async HTTP client, timeouts, mapping upstream failures to
our own error type (502), and caching so we don't hammer the provider.
"""
import httpx

from app.cache import cache
from app.config import settings
from app.exceptions import BadRequestError, ExternalServiceError

RATES_TTL_SECONDS = 60 * 60  # the provider only updates daily


async def fetch_rates(client: httpx.AsyncClient, base: str) -> tuple[dict, bool]:
    """Return (payload, from_cache)."""
    key = f"rates:{base}"
    cached = cache.get(key)
    if cached is not None:
        return cached, True

    try:
        response = await client.get(f"{settings.exchange_api_url}/{base}", timeout=10.0)
    except httpx.TimeoutException as exc:
        raise ExternalServiceError("Exchange-rate provider timed out.") from exc
    except httpx.HTTPError as exc:
        raise ExternalServiceError("Exchange-rate provider is unreachable.") from exc

    if response.status_code == 404:
        raise BadRequestError(f"Unsupported currency code '{base}'.")
    if response.status_code != 200:
        raise ExternalServiceError(f"Exchange-rate provider returned HTTP {response.status_code}.")

    data = response.json()
    if data.get("result") != "success" or "rates" not in data:
        raise BadRequestError(f"Unsupported currency code '{base}'.")

    payload = {"base": base, "rates": data["rates"], "provider_updated": data.get("time_last_update_utc")}
    cache.set(key, payload, RATES_TTL_SECONDS)
    return payload, False
