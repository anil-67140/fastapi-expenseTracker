"""Pydantic schemas = the public contract of the API.

Key idea (Response Models): the ORM `User` has `hashed_password`, but `UserOut`
does not. FastAPI filters every response through `response_model`, so the
password hash cannot leak even if a route returns the raw ORM object.
"""
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    PlainSerializer,
    computed_field,
    model_validator,
)

# Money is validated/stored as Decimal, but sent to clients as a plain JSON number.
Money = Annotated[Decimal, PlainSerializer(lambda v: float(v), return_type=float, when_used="json")]
CurrencyCode = Annotated[str, Field(pattern=r"^[A-Z]{3}$", examples=["USD"])]


class Category(StrEnum):
    food = "food"
    transport = "transport"
    housing = "housing"
    utilities = "utilities"
    health = "health"
    entertainment = "entertainment"
    shopping = "shopping"
    education = "education"
    other = "other"


class PaymentStatus(StrEnum):
    pending = "pending"
    paid = "paid"


class SortOrder(StrEnum):
    newest = "newest"
    oldest = "oldest"
    amount_desc = "amount_desc"
    amount_asc = "amount_asc"
    date_desc = "date_desc"
    date_asc = "date_asc"


# ---------------------------------------------------------------- errors
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail


_ERROR_DESCRIPTIONS = {
    400: "Bad request",
    401: "Missing, invalid or expired token",
    404: "Resource not found",
    409: "Conflict with existing data",
    413: "Uploaded file too large",
    415: "Unsupported file type",
    422: "Validation error",
    429: "Rate limit exceeded",
    502: "Upstream service failed",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """Document error responses in OpenAPI (/docs) with a shared model."""
    return {c: {"model": ErrorResponse, "description": _ERROR_DESCRIPTIONS[c]} for c in codes}


# ----------------------------------------------------------------- users
class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(str_strip_whitespace=True)


class UserOut(BaseModel):
    """What clients see. Note: no password, no hash."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    monthly_budget: Money
    currency: str
    created_at: datetime


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=120)
    monthly_budget: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    currency: CurrencyCode | None = None

    @model_validator(mode="after")
    def no_nulls(self) -> "UserUpdate":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Seconds until the token expires")


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    action: str
    entity: str
    entity_id: int | None
    created_at: datetime


# -------------------------------------------------------------- expenses
class ExpenseBase(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    title: str = Field(min_length=1, max_length=140, examples=["Groceries"])
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2, examples=["42.50"])
    category: Category = Category.other
    status: PaymentStatus = PaymentStatus.pending
    expense_date: date = Field(default_factory=date.today)
    notes: str | None = Field(default=None, max_length=500)


class ExpenseCreate(ExpenseBase):
    pass


class ExpenseUpdate(BaseModel):
    """PATCH body: every field optional; only fields the client sent are applied."""

    model_config = ConfigDict(str_strip_whitespace=True, use_enum_values=True)

    title: str | None = Field(default=None, min_length=1, max_length=140)
    amount: Decimal | None = Field(default=None, gt=0, max_digits=12, decimal_places=2)
    category: Category | None = None
    status: PaymentStatus | None = None
    expense_date: date | None = None
    notes: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def required_fields_not_null(self) -> "ExpenseUpdate":
        for name in ("title", "amount", "category", "status", "expense_date"):
            if name in self.model_fields_set and getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null")
        return self


class ExpenseOut(ExpenseBase):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: int
    amount: Money
    created_at: datetime
    updated_at: datetime
    # Internal storage name: excluded from output, exposed only as a URL below.
    receipt_filename: str | None = Field(default=None, exclude=True)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def receipt_url(self) -> str | None:
        return f"/uploads/{self.receipt_filename}" if self.receipt_filename else None


# ------------------------------------------------------------ pagination
T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_prev: bool


# ----------------------------------------------------------------- stats
class CategoryTotal(BaseModel):
    category: str
    total: Money
    count: int


class StatsOut(BaseModel):
    month: str = Field(description="YYYY-MM")
    currency: str
    expense_count: int
    total_spent: Money
    paid_total: Money
    pending_total: Money
    monthly_budget: Money
    budget_used_percent: float
    over_budget: bool
    by_category: list[CategoryTotal]


# -------------------------------------------------- third-party / crawler
class RatesOut(BaseModel):
    base: str
    rates: dict[str, float]
    provider_updated: str | None = None
    cached: bool


class ConvertOut(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    rate: float
    converted: float
    cached: bool


class CrawlRequest(BaseModel):
    urls: list[HttpUrl] = Field(min_length=1, max_length=5)


class CrawlResult(BaseModel):
    url: str
    ok: bool
    status_code: int | None = None
    title: str | None = None
    description: str | None = None
    headings: list[str] = []
    link_count: int = 0
    price_hints: list[str] = []
    error: str | None = None


class HealthOut(BaseModel):
    status: str
    database: str
    version: str
    environment: str
