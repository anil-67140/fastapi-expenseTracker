from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..domain import valid_category, valid_status
from ..schemas import ItemCreate, ItemRead, ItemStats

router = APIRouter(prefix="/api", tags=["api"])


@router.get("/items", response_model=list[ItemRead])
def get_items(db: Session = Depends(get_db)) -> list[ItemRead]:
    return crud.list_items(db)


@router.post("/items", response_model=ItemRead, status_code=status.HTTP_201_CREATED)
def create_item(payload: ItemCreate, db: Session = Depends(get_db)) -> ItemRead:
    if not valid_category(payload.category):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid category")
    if not valid_status(payload.status):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid status")
    return crud.create_item(db, payload)


@router.patch("/items/{item_id}/toggle", response_model=ItemRead)
def toggle_item(item_id: int, db: Session = Depends(get_db)) -> ItemRead:
    item = crud.toggle_item(db, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: int, db: Session = Depends(get_db)) -> None:
    deleted = crud.delete_item(db, item_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found")


@router.get("/stats", response_model=ItemStats)
def get_stats(db: Session = Depends(get_db)) -> ItemStats:
    return crud.get_stats(db)
