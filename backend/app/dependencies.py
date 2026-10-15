"""Dependency Injection: small reusable building blocks that routes declare as parameters.

FastAPI builds the dependency graph per request and caches each dependency, so
`CurrentUser` and `DbSession` inside `get_owned_expense` are the SAME objects the
route itself receives.
"""
from datetime import date
from decimal import Decimal
from typing import Annotated

import httpx
from fastapi import Depends, Query, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.exceptions import BadRequestError, NotFoundError, UnauthorizedError
from app.models import Expense, User
from app.pagination import PaginationParams
from app.schemas import Category, PaymentStatus, SortOrder
from app.security import decode_access_token

# `tokenUrl` powers the green "Authorize" button in /docs.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")

DbSession = Annotated[AsyncSession, Depends(get_db)]
Pagination = Annotated[PaginationParams, Depends()]


async def get_current_user(token: Annotated[str, Depends(oauth2_scheme)], db: DbSession) -> User:
    user_id = decode_access_token(token)
    user = await db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise UnauthorizedError("User no longer exists or is disabled.")
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_owned_expense(expense_id: int, user: CurrentUser, db: DbSession) -> Expense:
    """Load an expense that belongs to the caller.

    Someone else's expense returns 404 (not 403) so IDs of other users can't be probed.
    """
    expense = await db.scalar(select(Expense).where(Expense.id == expense_id, Expense.owner_id == user.id))
    if expense is None:
        raise NotFoundError(f"Expense {expense_id} not found.")
    return expense


OwnedExpense = Annotated[Expense, Depends(get_owned_expense)]


class ExpenseFilters:
    """Query-string filters for GET /expenses, grouped into one injectable object."""

    def __init__(
        self,
        q: Annotated[str | None, Query(max_length=100, description="Search title/notes")] = None,
        category: Category | None = None,
        status: PaymentStatus | None = None,
        min_amount: Annotated[Decimal | None, Query(ge=0)] = None,
        max_amount: Annotated[Decimal | None, Query(ge=0)] = None,
        date_from: date | None = None,
        date_to: date | None = None,
        sort: SortOrder = SortOrder.newest,
    ) -> None:
        if date_from and date_to and date_from > date_to:
            raise BadRequestError("date_from must be on or before date_to.")
        if min_amount is not None and max_amount is not None and min_amount > max_amount:
            raise BadRequestError("min_amount must be less than or equal to max_amount.")
        self.q = q.strip() if q else None
        self.category = category
        self.status = status
        self.min_amount = min_amount
        self.max_amount = max_amount
        self.date_from = date_from
        self.date_to = date_to
        self.sort = sort


Filters = Annotated[ExpenseFilters, Depends()]


async def get_http_client(request: Request) -> httpx.AsyncClient:
    """One shared AsyncClient (connection pooling) created in the app lifespan.

    Tests override this dependency with a client that returns canned responses.
    """
    return request.app.state.http_client


HttpClient = Annotated[httpx.AsyncClient, Depends(get_http_client)]
