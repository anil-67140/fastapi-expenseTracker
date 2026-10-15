"""Third-party API integration (currency exchange)."""
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response

from app.dependencies import CurrentUser, HttpClient
from app.exceptions import BadRequestError
from app.rate_limit import api_limiter
from app.schemas import ConvertOut, CurrencyCode, RatesOut, error_responses
from app.services.exchange import fetch_rates

router = APIRouter(prefix="/external", tags=["Third-party API"], dependencies=[Depends(api_limiter)])


@router.get("/rates", response_model=RatesOut, summary="Live exchange rates", responses=error_responses(400, 401, 429, 502))
async def rates(
    _user: CurrentUser,
    client: HttpClient,
    response: Response,
    base: Annotated[str, Query(pattern=r"^[A-Za-z]{3}$")] = "USD",
    symbols: Annotated[str | None, Query(description="Comma-separated codes to keep, e.g. EUR,GBP,PKR")] = None,
) -> RatesOut:
    data, cached = await fetch_rates(client, base.upper())
    chosen = data["rates"]
    if symbols:
        wanted = {s.strip().upper() for s in symbols.split(",") if s.strip()}
        chosen = {code: rate for code, rate in chosen.items() if code in wanted}
    response.headers["X-Cache"] = "HIT" if cached else "MISS"
    return RatesOut(base=data["base"], rates=chosen, provider_updated=data["provider_updated"], cached=cached)


@router.get("/convert", response_model=ConvertOut, summary="Convert an amount", responses=error_responses(400, 401, 422, 429, 502))
async def convert(
    _user: CurrentUser,
    client: HttpClient,
    amount: Annotated[float, Query(gt=0, le=1_000_000_000)],
    from_currency: Annotated[CurrencyCode, Query(alias="from")],
    to_currency: Annotated[CurrencyCode, Query(alias="to")],
) -> ConvertOut:
    data, cached = await fetch_rates(client, from_currency)
    rate = data["rates"].get(to_currency)
    if rate is None:
        raise BadRequestError(f"Unsupported currency code '{to_currency}'.")
    return ConvertOut(
        amount=amount,
        from_currency=from_currency,
        to_currency=to_currency,
        rate=rate,
        converted=round(amount * rate, 2),
        cached=cached,
    )
