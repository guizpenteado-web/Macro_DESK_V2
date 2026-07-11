from datetime import date, datetime

from pydantic import BaseModel


class AlertOut(BaseModel):
    id: int
    type: str
    severity: str
    title: str
    message: str | None = None
    entity_type: str | None = None
    entity_id: int | None = None
    ref_date: date
    is_read: bool
    created_at: datetime

    class Config:
        from_attributes = True
