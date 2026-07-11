from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CompanyBuyback, CompanySecurity
from app.schemas.buyback import BuybackOut

router = APIRouter(prefix="/api/buybacks", tags=["buybacks"])

BuybackSortField = Literal["ticker", "company_name", "declared_at", "deadline", "qty_common_shares", "qty_preferred_shares"]


@router.get("", response_model=list[BuybackOut])
def search_buybacks(
    search: str = Query("", min_length=0),
    status: Literal["Em Andamento", "Encerrado", ""] = "",
    limit: int = 100,
    sort_by: BuybackSortField = "declared_at",
    sort_dir: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
):
    # ticker "primario" por CNPJ = menor codigo alfabeticamente (MIN), que na
    # pratica cai na acao ON quando a empresa tem mais de uma classe listada
    # (ex: PETR3 antes de PETR4) — mesmo mapeamento ticker->CNPJ do FCA usado
    # na busca abaixo, ja que a CVM nunca inclui o ticker no dataset de recompra.
    primary_ticker = (
        select(CompanySecurity.cnpj_companhia, func.min(CompanySecurity.ticker).label("ticker"))
        .group_by(CompanySecurity.cnpj_companhia)
        .subquery()
    )

    stmt = select(CompanyBuyback, primary_ticker.c.ticker).outerjoin(
        primary_ticker, primary_ticker.c.cnpj_companhia == CompanyBuyback.cnpj
    )
    if search:
        cnpjs_by_ticker = select(CompanySecurity.cnpj_companhia).where(CompanySecurity.ticker.ilike(f"%{search}%"))
        stmt = stmt.where(
            CompanyBuyback.company_name.ilike(f"%{search}%")
            | CompanyBuyback.cnpj.ilike(f"%{search}%")
            | CompanyBuyback.cnpj.in_(cnpjs_by_ticker)
        )
    if status:
        stmt = stmt.where(CompanyBuyback.status == status)

    order_col = primary_ticker.c.ticker if sort_by == "ticker" else getattr(CompanyBuyback, sort_by)
    stmt = stmt.order_by(order_col.desc().nulls_last() if sort_dir == "desc" else order_col.asc().nulls_last()).limit(limit)

    results = []
    for buyback, ticker in db.execute(stmt).all():
        out = BuybackOut.model_validate(buyback)
        out.ticker = ticker
        results.append(out)
    return results
