"""Registration and login (OAuth2 password flow issuing JWT access tokens)."""
from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.dependencies import DbSession
from app.exceptions import ConflictError, UnauthorizedError
from app.models import User
from app.rate_limit import auth_limiter
from app.schemas import Token, UserCreate, UserOut, error_responses
from app.security import DUMMY_HASH, create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Authentication"], dependencies=[Depends(auth_limiter)])


@router.post(
    "/register",
    response_model=UserOut,  # <- hashed_password is filtered out here
    status_code=201,
    summary="Create an account",
    responses=error_responses(409, 422, 429),
)
async def register(payload: UserCreate, db: DbSession) -> User:
    email = payload.email.lower()
    if await db.scalar(select(User).where(User.email == email)):
        raise ConflictError("An account with this email already exists.")
    user = User(email=email, full_name=payload.full_name, hashed_password=hash_password(payload.password))
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:  # two simultaneous registrations: the DB unique index still protects us
        await db.rollback()
        raise ConflictError("An account with this email already exists.") from None
    await db.refresh(user)
    return user


@router.post(
    "/token",
    response_model=Token,
    summary="Log in (OAuth2 password flow)",
    description="Send `username` (your email) and `password` as form data. Returns a Bearer JWT.",
    responses=error_responses(401, 422, 429),
)
async def login(form: Annotated[OAuth2PasswordRequestForm, Depends()], db: DbSession) -> Token:
    user = await db.scalar(select(User).where(User.email == form.username.lower()))
    # Always run one hash verification so "unknown email" and "wrong password" take the same time.
    valid = verify_password(form.password, user.hashed_password if user else DUMMY_HASH)
    if not user or not valid or not user.is_active:
        raise UnauthorizedError("Incorrect email or password.")
    token, expires_in = create_access_token(str(user.id))
    return Token(access_token=token, expires_in=expires_in)
