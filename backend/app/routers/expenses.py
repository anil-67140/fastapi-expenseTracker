"""Expense CRUD with filtering, sorting, pagination, receipts and CSV export."""
import csv
import io
from collections.abc import Iterator

from fastapi import APIRouter, BackgroundTasks, Depends, Response, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import Select, func, or_, select

from app.cache import invalidate_user_cache
from app.dependencies import CurrentUser, DbSession, Filters, OwnedExpense, Pagination
from app.exceptions import BadRequestError
from app.models import Expense
from app.pagination import paginate
from app.rate_limit import api_limiter
from app.schemas import (
    ExpenseCreate,
    ExpenseOut,
    ExpenseUpdate,
    Page,
    PaymentStatus,
    SortOrder,
    error_responses,
)
from app.services import audit, storage

router = APIRouter(prefix="/expenses", tags=["Expenses"], dependencies=[Depends(api_limiter)])

SORT_COLUMNS = {
    SortOrder.newest: (Expense.created_at.desc(), Expense.id.desc()),
    SortOrder.oldest: (Expense.created_at.asc(), Expense.id.asc()),
    SortOrder.amount_desc: (Expense.amount.desc(), Expense.id.desc()),
    SortOrder.amount_asc: (Expense.amount.asc(), Expense.id.asc()),
    SortOrder.date_desc: (Expense.expense_date.desc(), Expense.id.desc()),
    SortOrder.date_asc: (Expense.expense_date.asc(), Expense.id.asc()),
}


def build_query(user_id: int, f) -> Select:
    stmt = select(Expense).where(Expense.owner_id == user_id)
    if f.q:
        needle = f.q.lower()
        stmt = stmt.where(
            or_(
                func.lower(Expense.title).contains(needle, autoescape=True),
                func.lower(func.coalesce(Expense.notes, "")).contains(needle, autoescape=True),
            )
        )
    if f.category:
        stmt = stmt.where(Expense.category == f.category.value)
    if f.status:
        stmt = stmt.where(Expense.status == f.status.value)
    if f.min_amount is not None:
        stmt = stmt.where(Expense.amount >= f.min_amount)
    if f.max_amount is not None:
        stmt = stmt.where(Expense.amount <= f.max_amount)
    if f.date_from:
        stmt = stmt.where(Expense.expense_date >= f.date_from)
    if f.date_to:
        stmt = stmt.where(Expense.expense_date <= f.date_to)
    return stmt.order_by(*SORT_COLUMNS[f.sort])


@router.post(
    "",
    response_model=ExpenseOut,
    status_code=201,  # 201 Created, not the default 200
    summary="Create an expense",
    responses=error_responses(401, 422, 429),
)
async def create_expense(
    payload: ExpenseCreate,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
    response: Response,
) -> Expense:
    expense = Expense(owner_id=user.id, **payload.model_dump())
    db.add(expense)
    await db.commit()
    await db.refresh(expense)
    invalidate_user_cache(user.id)
    background.add_task(audit.record_audit, user.id, "created", "expense", expense.id)
    response.headers["Location"] = f"/expenses/{expense.id}"  # REST convention for 201
    return expense


@router.get(
    "",
    response_model=Page[ExpenseOut],
    summary="List expenses (filter, sort, paginate)",
    responses=error_responses(400, 401, 422, 429),
)
async def list_expenses(user: CurrentUser, db: DbSession, filters: Filters, pagination: Pagination) -> dict:
    return await paginate(db, build_query(user.id, filters), pagination)


# NOTE: declared BEFORE "/{expense_id}" - otherwise "export" would be parsed as an int id and 422.
@router.get("/export/csv", summary="Download all expenses as CSV", responses=error_responses(401, 429))
async def export_csv(user: CurrentUser, db: DbSession) -> StreamingResponse:
    rows = (await db.scalars(select(Expense).where(Expense.owner_id == user.id).order_by(Expense.expense_date))).all()

    def safe(value: str) -> str:
        # CSV/formula injection: Excel would execute cells starting with = + - @
        return "'" + value if value[:1] in ("=", "+", "-", "@") else value

    def generate() -> Iterator[str]:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "date", "title", "category", "status", "amount", "notes"])
        yield buffer.getvalue()
        for e in rows:
            buffer.seek(0)
            buffer.truncate()
            writer.writerow([e.id, e.expense_date, safe(e.title), e.category, e.status, f"{e.amount:.2f}", safe(e.notes or "")])
            yield buffer.getvalue()

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="expenses.csv"'},
    )


@router.get("/{expense_id}", response_model=ExpenseOut, responses=error_responses(401, 404, 429))
async def get_expense(expense: OwnedExpense) -> Expense:
    return expense


@router.patch("/{expense_id}", response_model=ExpenseOut, responses=error_responses(400, 401, 404, 422, 429))
async def update_expense(
    payload: ExpenseUpdate, expense: OwnedExpense, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> Expense:
    changes = payload.model_dump(exclude_unset=True)  # only what the client actually sent
    if not changes:
        raise BadRequestError("Send at least one field to update.")
    for field, value in changes.items():
        setattr(expense, field, value)
    await db.commit()
    await db.refresh(expense)
    invalidate_user_cache(user.id)
    background.add_task(audit.record_audit, user.id, "updated", "expense", expense.id)
    return expense


@router.patch("/{expense_id}/toggle", response_model=ExpenseOut, summary="Flip pending <-> paid", responses=error_responses(401, 404, 429))
async def toggle_expense(expense: OwnedExpense, user: CurrentUser, db: DbSession, background: BackgroundTasks) -> Expense:
    expense.status = PaymentStatus.pending.value if expense.status == PaymentStatus.paid.value else PaymentStatus.paid.value
    await db.commit()
    await db.refresh(expense)
    invalidate_user_cache(user.id)
    background.add_task(audit.record_audit, user.id, f"marked {expense.status}", "expense", expense.id)
    return expense


@router.delete("/{expense_id}", status_code=204, summary="Delete an expense", responses=error_responses(401, 404, 429))
async def delete_expense(expense: OwnedExpense, user: CurrentUser, db: DbSession, background: BackgroundTasks) -> Response:
    receipt, expense_id = expense.receipt_filename, expense.id
    await db.delete(expense)
    await db.commit()
    await storage.delete_receipt(receipt)
    invalidate_user_cache(user.id)
    background.add_task(audit.record_audit, user.id, "deleted", "expense", expense_id)
    return Response(status_code=204)  # 204 = success with an empty body


@router.post(
    "/{expense_id}/receipt",
    response_model=ExpenseOut,
    summary="Attach a receipt (jpg, png, webp or pdf)",
    responses=error_responses(401, 404, 413, 415, 429),
)
async def upload_receipt(
    file: UploadFile, expense: OwnedExpense, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> Expense:
    new_name = await storage.save_receipt(file)
    old_name, expense.receipt_filename = expense.receipt_filename, new_name
    await db.commit()
    await db.refresh(expense)
    await storage.delete_receipt(old_name)  # replace, don't accumulate
    background.add_task(audit.record_audit, user.id, "attached receipt", "expense", expense.id)
    return expense
