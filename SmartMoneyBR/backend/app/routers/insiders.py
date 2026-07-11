from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CompanySecurity, InsiderTrade
from app.schemas.insider import InsiderTradeOut

router = APIRouter(prefix="/api/insiders", tags=["insiders"])

InsiderSortField = Literal["data_movimentacao", "ticker", "company_name", "quantidade", "volume", "preco_unitario"]


@router.get("", response_model=list[InsiderTradeOut])
def search_insider_trades(
    search: str = Query("", min_length=0),
    direction: Literal["COMPRA", "VENDA", ""] = "",
    cargo: str = Query("", min_length=0),
    date_from: date | None = None,
    date_to: date | None = None,
    only_dated: bool = True,
    limit: int = 100,
    sort_by: InsiderSortField = "data_movimentacao",
    sort_dir: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
):
    """only_dated=True (default) excludes 'Saldo Inicial' and other rows
    without Data_Movimentacao — those aren't dated trading events, just
    opening-of-office balances, and would otherwise dominate any date-sorted
    list as nulls."""
    # mesmo mapeamento ticker->CNPJ (via FCA/CompanySecurity) usado em
    # buybacks.py — VLMO tambem so traz CNPJ+razao social, nunca o ticker.
    primary_ticker = (
        select(CompanySecurity.cnpj_companhia, func.min(CompanySecurity.ticker).label("ticker"))
        .group_by(CompanySecurity.cnpj_companhia)
        .subquery()
    )

    stmt = select(InsiderTrade, primary_ticker.c.ticker).outerjoin(
        primary_ticker, primary_ticker.c.cnpj_companhia == InsiderTrade.cnpj_companhia
    )
    if search:
        cnpjs_by_ticker = select(CompanySecurity.cnpj_companhia).where(CompanySecurity.ticker.ilike(f"%{search}%"))
        stmt = stmt.where(
            InsiderTrade.company_name.ilike(f"%{search}%")
            | InsiderTrade.cnpj_companhia.ilike(f"%{search}%")
            | InsiderTrade.cnpj_companhia.in_(cnpjs_by_ticker)
        )
    if direction:
        stmt = stmt.where(InsiderTrade.direction == direction)
    if cargo:
        stmt = stmt.where(InsiderTrade.tipo_cargo == cargo)
    if date_from is not None:
        stmt = stmt.where(InsiderTrade.data_movimentacao >= date_from)
    if date_to is not None:
        stmt = stmt.where(InsiderTrade.data_movimentacao <= date_to)
    if only_dated:
        stmt = stmt.where(InsiderTrade.data_movimentacao.is_not(None))

    order_col = primary_ticker.c.ticker if sort_by == "ticker" else getattr(InsiderTrade, sort_by)
    stmt = stmt.order_by(order_col.desc().nulls_last() if sort_dir == "desc" else order_col.asc().nulls_last()).limit(limit)

    results = []
    for trade, ticker in db.execute(stmt).all():
        out = InsiderTradeOut.model_validate(trade)
        out.ticker = ticker
        results.append(out)
    return results


@router.get("/cargos", response_model=list[str])
def list_cargos(db: Session = Depends(get_db)):
    rows = db.execute(
        select(InsiderTrade.tipo_cargo).where(InsiderTrade.tipo_cargo.is_not(None)).distinct().order_by(InsiderTrade.tipo_cargo)
    ).scalars()
    return list(rows)
