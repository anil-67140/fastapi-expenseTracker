from datetime import datetime

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from .models import Item
from .schemas import ItemCreate, ItemStats

def list_items(db: Session) -> list[Item]:
    query = (
        select(Item)
        .order_by(Item.is_done.asc())
        .order_by(Item.target_date.is_(None), Item.target_date.asc())
        .order_by(Item.created_at.desc())
    )
    return list(db.scalars(query).all())

def get_item(db: Session, item_id: int) -> Item | None:
    return db.get(Item, item_id)

def create_item(db: Session, payload: ItemCreate) -> Item:
    item = Item(
        title=payload.title.strip(),
        description=(payload.description or "").strip() or None,
        category=payload.category,
        status=payload.status,
        priority=payload.priority,
        target_date=payload.target_date,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item

def toggle_item(db: Session, item_id: int) -> Item | None:
    item = get_item(db, item_id)
    if item is None:
        return None

    item.is_done = not item.is_done
    item.completed_at = datetime.utcnow() if item.is_done else None

    db.commit()
    db.refresh(item)
    return item

def delete_item(db: Session, item_id: int) -> bool:
    item = get_item(db, item_id)
    if item is None:
        return False

    db.delete(item)
    db.commit()
    return True

def get_stats(db: Session) -> ItemStats:
    total = db.scalar(select(func.count()).select_from(Item)) or 0
    completed = db.scalar(select(func.count()).select_from(Item).where(Item.is_done.is_(True))) or 0
    in_progress = total - completed
    completion_rate = round((completed / total) * 100, 1) if total else 0.0

    score_stmt = select(
        func.coalesce(
            func.sum(case((Item.is_done.is_(True), Item.priority * 10), else_=0)),
            0,
        )
    )
    impact_score = db.scalar(score_stmt) or 0

    return ItemStats(
        total=total,
        completed=completed,
        in_progress=in_progress,
        completion_rate=completion_rate,
        impact_score=impact_score,
    )
