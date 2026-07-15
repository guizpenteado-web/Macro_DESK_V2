"""Caches B3 COTAHIST daily OHLC into asset_price_history, on demand — a
year is ingested (all ~300-500 tickers at once, not just the one requested)
the first time ANY ticker needs it, so later requests for other tickers in
an already-cached year are instant. The current (still-trading) year is
re-fetched if our cache is more than a day old; closed years never change."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import AssetPriceHistory, IngestionLog
from app.services.b3_client import download_cotahist_year
from app.services.cotahist_parser import parse_cotahist_zip

logger = logging.getLogger(__name__)

CURRENT_YEAR_STALE_AFTER = timedelta(days=1)


def ingest_cotahist_year(db: Session, year: int, force_download: bool = False) -> int:
    """Ingest one full calendar year of B3 daily OHLC (all tickers at once).
    Idempotent — safe to call again (upsert on ticker+trade_date)."""
    log = IngestionLog(source="cotahist", ref_date=date(year, 12, 31), status="running")
    db.add(log)
    db.flush()

    try:
        zip_path = download_cotahist_year(year, force=force_download)
        parsed = parse_cotahist_zip(zip_path)
        rows = [{**r, "ingested_at": datetime.utcnow()} for r in parsed]

        if rows:
            stmt = pg_insert(AssetPriceHistory).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_asset_price_ticker_date",
                set_={
                    "open": stmt.excluded.open,
                    "high": stmt.excluded.high,
                    "low": stmt.excluded.low,
                    "close": stmt.excluded.close,
                    "volume": stmt.excluded.volume,
                    "ingested_at": stmt.excluded.ingested_at,
                },
            )
            db.execute(stmt)

        db.commit()
        log.status = "success"
        log.rows_processed = len(rows)
        log.finished_at = datetime.utcnow()
        db.commit()
        logger.info("cotahist %d: ok — %d linhas (%d tickers)", year, len(rows), len({r["ticker"] for r in rows}))
        return len(rows)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        log.status = "failed"
        log.error_message = str(exc)[:2000]
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        logger.exception("cotahist %d: falhou", year)
        raise


def _year_needs_ingestion(db: Session, year: int) -> bool:
    last_log = db.execute(
        select(IngestionLog)
        .where(IngestionLog.source == "cotahist", IngestionLog.ref_date == date(year, 12, 31), IngestionLog.status == "success")
        .order_by(IngestionLog.finished_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    if last_log is None:
        return True
    if year == date.today().year:
        return datetime.utcnow() - last_log.finished_at > CURRENT_YEAR_STALE_AFTER
    return False


def get_price_history(db: Session, ticker: str, years: int = 10) -> list[AssetPriceHistory]:
    """Ensures every needed year is cached (ingesting on demand whatever's
    missing/stale), then returns the ticker's daily OHLC for the window."""
    ticker = ticker.upper().strip()
    current_year = date.today().year
    start_year = current_year - years + 1

    for year in range(start_year, current_year + 1):
        if not _year_needs_ingestion(db, year):
            continue
        try:
            ingest_cotahist_year(db, year, force_download=(year == current_year))
        except Exception:
            logger.warning("cotahist %d indisponivel, seguindo sem esse ano", year)

    cutoff = date(start_year, 1, 1)
    return db.execute(
        select(AssetPriceHistory)
        .where(AssetPriceHistory.ticker == ticker, AssetPriceHistory.trade_date >= cutoff)
        .order_by(AssetPriceHistory.trade_date)
    ).scalars().all()


# COTAHIST e' o arquivo historico OFICIAL da B3 — de proposito nao ajustado
# por desdobramento/grupamento/bonificacao, reflete o preco literal do
# pregao naquele dia. Qualquer split no meio dos anos pedidos aparece como
# um "penhasco" no preco (achado 14/jul/2026: B3SA3 caiu 67.2% num unico dia
# em 17/05/2021 — desdobramento 3-por-1, nao um crash real — e o candlestick
# de 10 anos ficava com metade "estourada" la em cima e a outra metade
# espremida la embaixo). Sem um dataset de proventos/eventos societarios da
# B3 no pipeline, a correcao e' heuristica: um salto de fechamento pra
# fechamento que bate (com folga) numa razao "redonda" (2x, 3x, 1/2, 1/3...)
# e' tratado como split, nao como movimento de preco real — plausivel pra
# acao liquida negociada por fundo (o universo desse app), quase impossivel
# ser noise de mercado genuino.
_SPLIT_RATIOS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 50, 100]
_SPLIT_TOLERANCE = 0.06


def _detect_split_ratio(prev_close: float, close: float) -> float | None:
    if prev_close <= 0 or close <= 0:
        return None
    ratio = close / prev_close
    for r in _SPLIT_RATIOS:
        if abs(ratio - 1 / r) <= (1 / r) * _SPLIT_TOLERANCE:
            return 1 / r
        if abs(ratio - r) <= r * _SPLIT_TOLERANCE:
            return float(r)
    return None


def adjust_for_splits(rows: list[AssetPriceHistory]) -> list[dict]:
    """rows precisam vir ordenados por trade_date ascendente. Devolve dicts
    (nao ORM objects) com OHLC ajustado pra ficar continuo em termos de
    quantidade de acao de HOJE — o dia mais recente nunca muda, dias mais
    antigos que um split detectado sao multiplicados pelo fator acumulado."""
    if len(rows) < 2:
        return [
            {
                "date": r.trade_date,
                "open": float(r.open),
                "high": float(r.high),
                "low": float(r.low),
                "close": float(r.close),
                "volume": float(r.volume) if r.volume is not None else None,
            }
            for r in rows
        ]

    closes = [float(r.close) for r in rows]
    split_at: dict[int, float] = {}
    for i in range(1, len(closes)):
        ratio = _detect_split_ratio(closes[i - 1], closes[i])
        if ratio is not None:
            split_at[i] = ratio

    n = len(rows)
    factors = [1.0] * n
    factor = 1.0
    for i in range(n - 1, 0, -1):
        if i in split_at:
            factor *= split_at[i]
        factors[i - 1] = factor

    return [
        {
            "date": r.trade_date,
            "open": float(r.open) * factors[i],
            "high": float(r.high) * factors[i],
            "low": float(r.low) * factors[i],
            "close": float(r.close) * factors[i],
            "volume": float(r.volume) if r.volume is not None else None,
        }
        for i, r in enumerate(rows)
    ]
