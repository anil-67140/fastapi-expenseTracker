from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ItemBase(BaseModel):
    title: str = Field(min_length=1, max_length=140)
    description: str | None = Field(default=None, max_length=2000)
    category: str = Field(min_length=1, max_length=40)
    status: str = Field(min_length=1, max_length=40)
    priority: int = Field(default=3, ge=1, le=5)
    target_date: date | None = None


class ItemCreate(ItemBase):
    pass


class ItemRead(ItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_done: bool
    created_at: datetime
    completed_at: datetime | None


class ItemStats(BaseModel):
    total: int
    completed: int
    in_progress: int
    completion_rate: float
    impact_score: int
