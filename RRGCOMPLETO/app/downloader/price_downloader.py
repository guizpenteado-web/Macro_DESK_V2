"""
Download incremental de preços OHLCV via yfinance.
Só baixa datas novas (após o último registro no banco). Inclui o IBOV
(^BVSP) como ticker especial "IBOV" — é sempre o benchmark de comparação.

Adaptado do padrão em Market_BREADTH_ULTRA/app/downloader/price_downloader.py.
"""
from __future__ import annotations
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repository import AssetRepository, PriceRepository
from app.utils.logger import logger

IBOV_TICKER = "IBOV"
_IBOV_YF_SYMBOL = "^BVSP"


def _to_yf(ticker: str) -> str:
    if ticker == IBOV_TICKER:
        return _IBOV_YF_SYMBOL
    return ticker if ticker.endswith(".SA") else f"{ticker}.SA"


def _latest_date(ticker: str) -> str:
    with get_session() as s:
        d = PriceRepository(s).get_latest_date(ticker)
    if d:
        return (d + timedelta(days=1)).isoformat()
    return settings.download_start_date


def _download_one(ticker: str) -> tuple[str, pd.DataFrame]:
    start = _latest_date(ticker)
    today = date.today().isoformat()
    if start > today:
        return ticker, pd.DataFrame()
    try:
        # auto_adjust=False (achado 15/jul/2026) — com True (default do
        # yfinance moderno) o Close vem ajustado por dividendo/split, mas o
        # grafico do TradingView (usado no indicador Pine) mostra preco BRUTO
        # por padrao. Fundo que paga dividendo regular (ex: UGPA3) cria um
        # degrau artificial toda vez que ajusta retroativamente, divergindo
        # cada vez mais do RS-Ratio calculado sobre o preco cru do Pine —
        # usuario reportou "diverge bastante" no D1. Preco bruto tambem bate
        # com o proprio COTAHIST da B3 usado no resto do Hub (SmartMoneyBR).
        df = yf.download(
            _to_yf(ticker), start=start, end=today,
            progress=False, auto_adjust=False, actions=False,
        )
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return ticker, df
    except Exception as e:
        logger.error(f"{ticker} download error: {e}")
        return ticker, pd.DataFrame()


def _df_to_rows(ticker: str, df: pd.DataFrame) -> list[dict]:
    rows = []
    for idx, row in df.iterrows():
        d = idx.date() if hasattr(idx, "date") else idx
        close = float(row.get("Close", 0) or 0)
        if close <= 0:
            continue
        rows.append({
            "ticker": ticker, "date": d,
            "open": float(row.get("Open", 0) or 0) or None,
            "high": float(row.get("High", 0) or 0) or None,
            "low": float(row.get("Low", 0) or 0) or None,
            "close": close,
            "volume": float(row.get("Volume", 0) or 0) or None,
        })
    return rows


def update_prices(tickers: Optional[list[str]] = None) -> dict[str, int]:
    """Download incremental para todos (ou subset) dos ativos + IBOV. Retorna {ticker: rows}."""
    if tickers is None:
        with get_session() as s:
            tickers = AssetRepository(s).get_active_tickers()
    tickers = list(tickers) + [IBOV_TICKER]
    if not tickers:
        logger.warning("Nenhum ativo no banco. Sincronize os componentes primeiro.")
        return {}

    results: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=settings.download_max_workers) as ex:
        futures = {ex.submit(_download_one, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                _, df = future.result()
                if df.empty:
                    results[ticker] = 0
                    continue
                rows = _df_to_rows(ticker, df)
                with get_session() as s:
                    n = PriceRepository(s).bulk_upsert(rows)
                results[ticker] = n
                if n > 0:
                    logger.debug(f"{ticker}: {n} precos salvos")
            except Exception as e:
                logger.error(f"{ticker}: {e}")
                results[ticker] = -1

    ok = sum(1 for v in results.values() if v >= 0)
    tot = sum(v for v in results.values() if v > 0)
    logger.success(f"Download: {ok}/{len(tickers)} ativos OK | {tot} novos precos")
    return results
