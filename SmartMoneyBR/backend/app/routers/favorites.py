from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import FundFavorite

router = APIRouter(prefix="/api/favorites", tags=["favorites"])


@router.get("", response_model=list[int])
def list_favorites(db: Session = Depends(get_db)):
    """So os fund_id — a pagina de Favoritos busca o detalhe de cada fundo
    via GET /api/funds/{id}, ja existente, em vez de duplicar aqui a logica
    de NAV/retorno que aquele endpoint ja calcula."""
    rows = db.execute(select(FundFavorite.fund_id).order_by(FundFavorite.favorited_at.desc())).scalars().all()
    return list(rows)


@router.post("/{fund_id}")
def add_favorite(fund_id: int, db: Session = Depends(get_db)):
    stmt = pg_insert(FundFavorite).values(fund_id=fund_id).on_conflict_do_nothing()
    db.execute(stmt)
    db.commit()
    return {"ok": True}


@router.delete("/{fund_id}")
def remove_favorite(fund_id: int, db: Session = Depends(get_db)):
    obj = db.get(FundFavorite, fund_id)
    if obj:
        db.delete(obj)
        db.commit()
    return {"ok": True}
