"""Dashboard numbers. Cached for a short time and invalidated on every write."""
from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy import func, select

from app.cache import cache
from app.config import settings
from app.dependencies import CurrentUser, DbSession
from app.models import Expense
from app.rate_limit import api_limiter
from app.schemas import CategoryTotal, PaymentStatus, StatsOut, error_responses

router = APIRouter(prefix="/stats", tags=["Statistics"], dependencies=[Depends(api_limiter)])


def _dec(value) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.01"))


@router.get("", response_model=StatsOut, summary="Monthly totals and budget pressure", responses=error_responses(401, 422, 429))
async def get_stats(
    user: CurrentUser,
    db: DbSession,
    response: Response,
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$", description="YYYY-MM, defaults to this month")] = None,
) -> StatsOut:
    today = date.today()
    month = month or f"{today.year:04d}-{today.month:02d}"

    key = f"user:{user.id}:stats:{month}"
    cached = cache.get(key)
    if cached is not None:
        response.headers["X-Cache"] = "HIT"
        return cached
    response.headers["X-Cache"] = "MISS"

    year, mon = int(month[:4]), int(month[5:])
    start = date(year, mon, 1)
    end = date(year + (mon == 12), mon % 12 + 1, 1)
    in_month = (Expense.owner_id == user.id, Expense.expense_date >= start, Expense.expense_date < end)

    by_status = {
        status: (_dec(total), count)
        for status, total, count in (
            await db.execute(select(Expense.status, func.sum(Expense.amount), func.count()).where(*in_month).group_by(Expense.status))
        ).all()
    }
    category_rows = (
        await db.execute(
            select(Expense.category, func.sum(Expense.amount).label("total"), func.count())
            .where(*in_month)
            .group_by(Expense.category)
            .order_by(func.sum(Expense.amount).desc())
        )
    ).all()

    paid = by_status.get(PaymentStatus.paid.value, (Decimal("0"), 0))[0]
    pending = by_status.get(PaymentStatus.pending.value, (Decimal("0"), 0))[0]
    total = paid + pending
    budget = _dec(user.monthly_budget)
    used = float(round(total / budget * 100, 1)) if budget else 0.0

    stats = StatsOut(
        month=month,
        currency=user.currency,
        expense_count=sum(count for _, count in by_status.values()),
        total_spent=total,
        paid_total=paid,
        pending_total=pending,
        monthly_budget=budget,
        budget_used_percent=used,
        over_budget=total > budget,
        by_category=[CategoryTotal(category=c, total=_dec(t), count=n) for c, t, n in category_rows],
    )
    cache.set(key, stats, settings.cache_ttl_seconds)
    return stats
