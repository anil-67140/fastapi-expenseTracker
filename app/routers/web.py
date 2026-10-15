from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from .. import crud
from ..database import get_db
from ..domain import DOMAIN_CONFIG, valid_category, valid_status
from ..schemas import ItemCreate

router = APIRouter(tags=["web"])

BASE_DIR = Path(__file__).resolve().parent.parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))



@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    items = crud.list_items(db)
    stats = crud.get_stats(db)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "items": items,
            "stats": stats,
            "today": datetime.utcnow().date(),
            "config": DOMAIN_CONFIG,
        },
    )

@router.post("/items")
def create_item(
    title: str = Form(...),
    description: str = Form(""),
    category: str = Form(...),
    status: str = Form(...),
    priority: int = Form(3),
    target_date: str = Form(""),
    db: Session = Depends(get_db),
) -> RedirectResponse:
    clean_title = title.strip()
    if not clean_title:
        return RedirectResponse(url="/", status_code=303)

    if not valid_category(category):
        category = DOMAIN_CONFIG.category_options[0]
    if not valid_status(status):
        status = DOMAIN_CONFIG.status_options[0]

    date_value = None
    if target_date:
        try:
            date_value = datetime.strptime(target_date, "%Y-%m-%d").date()
        except ValueError:
            date_value = None

    payload = ItemCreate(
        title=clean_title,
        description=description.strip() or None,
        category=category,
        status=status,
        priority=max(1, min(int(priority), 5)),
        target_date=date_value,
    )
    crud.create_item(db, payload)
    return RedirectResponse(url="/", status_code=303)


@router.post("/items/{item_id}/toggle")
def toggle_item(item_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    crud.toggle_item(db, item_id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/items/{item_id}/delete")
def delete_item(item_id: int, db: Session = Depends(get_db)) -> RedirectResponse:
    crud.delete_item(db, item_id)
    return RedirectResponse(url="/", status_code=303)
