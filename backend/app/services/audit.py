"""Audit trail. Called through BackgroundTasks, so it runs AFTER the response is sent.

A background task cannot reuse the request's DB session (it is closed by then),
so it opens its own.
"""
import logging

from app.database import SessionLocal
from app.models import AuditLog

logger = logging.getLogger("app.audit")


async def record_audit(user_id: int, action: str, entity: str, entity_id: int | None = None) -> None:
    try:
        async with SessionLocal() as session:
            session.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id))
            await session.commit()
    except Exception:  # never let a background task crash noisily
        logger.exception("Failed to write audit log")
