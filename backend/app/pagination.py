"""Reusable pagination: a query-param dependency + a helper that builds a `Page`."""
import math
from typing import Annotated, Any

from fastapi import Query
from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class PaginationParams:
    def __init__(
        self,
        page: Annotated[int, Query(ge=1, description="1-based page number")] = 1,
        page_size: Annotated[int, Query(ge=1, le=100, description="Items per page (max 100)")] = 10,
    ) -> None:
        self.page = page
        self.page_size = page_size

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


async def paginate(db: AsyncSession, stmt: Select[Any], params: PaginationParams) -> dict[str, Any]:
    """Run COUNT(*) for the total, then LIMIT/OFFSET for the slice.

    Returns a plain dict shaped like `schemas.Page`; the route's `response_model`
    validates it and converts ORM rows into the public schema.
    """
    total = await db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = (await db.scalars(stmt.limit(params.page_size).offset(params.offset))).all()
    pages = max(1, math.ceil(total / params.page_size))
    return {
        "items": list(rows),
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "pages": pages,
        "has_next": params.page < pages,
        "has_prev": params.page > 1,
    }
