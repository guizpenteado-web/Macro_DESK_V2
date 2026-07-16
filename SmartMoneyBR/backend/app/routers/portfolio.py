from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PortfolioItem

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def current_username(request: Request) -> str:
    """Le a identidade repassada pelo unified_server.py (header X-Hub-Username,
    setado a partir da sessao de login do Hub). Diferente de Favoritos, a
    Carteira e' pessoal por usuario — sem essa identidade nao ha lista pra
    mostrar, entao exige o header (presente sempre que se acessa via Hub)."""
    username = request.headers.get("x-hub-username", "").strip()
    if not username:
        raise HTTPException(status_code=401, detail="Carteira exige login no Hub.")
    return username


@router.get("", response_model=list[int])
def list_portfolio(username: str = Depends(current_username), db: Session = Depends(get_db)):
    """So os asset_id — a pagina de Carteira busca o detalhe de cada ativo
    via GET /api/assets/{id}, ja existente, mesmo padrao de Favoritos."""
    rows = db.execute(
        select(PortfolioItem.asset_id)
        .where(PortfolioItem.owner_username == username)
        .order_by(PortfolioItem.added_at.desc())
    ).scalars().all()
    return list(rows)


@router.post("/{asset_id}")
def add_to_portfolio(asset_id: int, username: str = Depends(current_username), db: Session = Depends(get_db)):
    stmt = pg_insert(PortfolioItem).values(owner_username=username, asset_id=asset_id).on_conflict_do_nothing()
    db.execute(stmt)
    db.commit()
    return {"ok": True}


@router.delete("/{asset_id}")
def remove_from_portfolio(asset_id: int, username: str = Depends(current_username), db: Session = Depends(get_db)):
    obj = db.execute(
        select(PortfolioItem).where(PortfolioItem.owner_username == username, PortfolioItem.asset_id == asset_id)
    ).scalar_one_or_none()
    if obj:
        db.delete(obj)
        db.commit()
    return {"ok": True}
