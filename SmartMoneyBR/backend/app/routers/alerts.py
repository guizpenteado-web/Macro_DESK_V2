from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Alert
from app.schemas.alert import AlertOut
from app.services.alert_engine import generate_all_alerts

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertOut])
def list_alerts(
    only_unread: bool = False,
    type: str = Query("", min_length=0),
    search: str = Query("", min_length=0),
    limit: int = 100,
    db: Session = Depends(get_db),
):
    stmt = select(Alert)
    if only_unread:
        stmt = stmt.where(Alert.is_read.is_(False))
    if type:
        stmt = stmt.where(Alert.type == type)
    if search:
        like = f"%{search}%"
        stmt = stmt.where(or_(Alert.title.ilike(like), Alert.message.ilike(like)))
    stmt = stmt.order_by(Alert.ref_date.desc(), Alert.created_at.desc()).limit(limit)
    return db.execute(stmt).scalars().all()


@router.get("/unread-count")
def unread_count(db: Session = Depends(get_db)):
    n = db.execute(select(func.count()).select_from(Alert).where(Alert.is_read.is_(False))).scalar_one()
    return {"unread": n}


@router.post("/{alert_id}/read", response_model=AlertOut)
def mark_read(alert_id: int, db: Session = Depends(get_db)):
    alert = db.get(Alert, alert_id)
    if not alert:
        raise HTTPException(404, "Alerta nao encontrado")
    alert.is_read = True
    db.commit()
    db.refresh(alert)
    return alert


@router.post("/read-all")
def mark_all_read(db: Session = Depends(get_db)):
    db.execute(update(Alert).where(Alert.is_read.is_(False)).values(is_read=True))
    db.commit()
    return {"ok": True}


@router.post("/generate")
def trigger_generation(db: Session = Depends(get_db)):
    """Dispara o motor de alertas manualmente (tambem roda automaticamente
    depois de cada job agendado de ingestao)."""
    return generate_all_alerts(db)
