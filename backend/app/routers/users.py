"""The signed-in user's profile and recent activity."""
from fastapi import APIRouter, Depends
from sqlalchemy import select

from app.cache import invalidate_user_cache
from app.dependencies import CurrentUser, DbSession
from app.exceptions import BadRequestError
from app.models import AuditLog, User
from app.rate_limit import api_limiter
from app.schemas import ActivityOut, UserOut, UserUpdate, error_responses

router = APIRouter(prefix="/users", tags=["Users"], dependencies=[Depends(api_limiter)])


@router.get("/me", response_model=UserOut, responses=error_responses(401))
async def read_me(user: CurrentUser) -> User:
    return user


@router.patch("/me", response_model=UserOut, responses=error_responses(400, 401, 422))
async def update_me(payload: UserUpdate, user: CurrentUser, db: DbSession) -> User:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        raise BadRequestError("Send at least one field to update.")
    for field, value in changes.items():
        setattr(user, field, value)
    await db.commit()
    invalidate_user_cache(user.id)  # budget changed -> cached stats are stale
    return user


@router.get("/me/activity", response_model=list[ActivityOut], responses=error_responses(401))
async def recent_activity(user: CurrentUser, db: DbSession, limit: int = 10) -> list[AuditLog]:
    """Entries written by background tasks."""
    limit = max(1, min(limit, 50))
    result = await db.scalars(
        select(AuditLog).where(AuditLog.user_id == user.id).order_by(AuditLog.id.desc()).limit(limit)
    )
    return list(result.all())
