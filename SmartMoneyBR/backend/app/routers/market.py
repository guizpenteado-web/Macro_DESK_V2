from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.services.price_ingestion import adjust_for_splits, get_price_history

router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/price-history")
def price_history(ticker: str = Query(..., min_length=1), years: int = 10, db: Session = Depends(get_db)):
    """Daily OHLC candlestick data, sourced from B3's own COTAHIST files
    (not the CVM datasets used elsewhere in this app) — see
    app/services/price_ingestion.py. Empty list if B3 has no round-lot
    equity trading data for this ticker (delisted, FII, wrong code, etc.).
    COTAHIST e' cru (nao ajustado por split) — adjust_for_splits corrige
    heuristicamente antes de servir pro grafico (achado 14/jul/2026)."""
    rows = get_price_history(db, ticker, years=years)
    return adjust_for_splits(rows)
