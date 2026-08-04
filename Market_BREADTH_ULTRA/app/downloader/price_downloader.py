"""
Download incremental de precos OHLCV via yfinance.
So baixa datas novas (apos o ultimo registro no banco).
"""
from __future__ import annotations
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from typing import Optional
import pandas as pd
import yfinance as yf
from app.config.settings import settings
from app.database.connection import get_session
from app.database.repository import AssetRepository, PriceRepository
from app.utils.logger import logger

def _to_yf(ticker: str) -> str:
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
        # auto_adjust=False (achado 04/ago/2026, mesmo bug ja corrigido em
        # RRGCOMPLETO/app/downloader/price_downloader.py em 15/jul/2026) —
        # com True (default do yfinance moderno) o OHLC vem retroativamente
        # ajustado por dividendo/split, nao e o preco realmente negociado no
        # pregao. Ativo que paga provento regular cria um "degrau" toda vez
        # que o historico e reajustado pra tras, divergindo cada vez mais do
        # candle bruto que qualquer plataforma (home broker, TradingView)
        # mostra por padrao — era a causa do "parecido mas nao identico"
        # reportado na aba Frequency do Market Breadth.
        df = yf.download(_to_yf(ticker), start=start, end=today,
                         progress=False, auto_adjust=False, actions=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        return ticker, df
    except Exception as e:
        logger.error(f"{ticker} download error: {e}")
        return ticker, pd.DataFrame()

def _is_missing(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v))

def _df_to_rows(ticker: str, df: pd.DataFrame) -> list[dict]:
    rows = []
    for idx, row in df.iterrows():
        d = idx.date() if hasattr(idx,"date") else idx
        close_raw = row.get("Close")
        # Close vem NaN (nao 0) no pregao mais recente quando o Yahoo ainda
        # nao fechou o candle oficialmente (achado 04/ago/2026, ex: EMBJ3
        # 03/ago com Open/High/Low/Volume validos mas Close=NaN) — o check
        # antigo "close <= 0" nao pega NaN (comparacao com NaN e sempre
        # False), o que deixava close=NaN entrar no INSERT e estourar a
        # constraint NOT NULL. Pula o dia, o proximo update pega ele pronto.
        if _is_missing(close_raw):
            continue
        close = float(close_raw)
        if close <= 0:
            continue
        # Yahoo as vezes devolve Open/High/Low = 0 ou NaN (glitch de feed) num
        # pregao com Close valido — guardar null ali quebra o candle no
        # grafico (achado 04/ago/2026, ~78/202 tickers em datas pontuais).
        # Preenche com o close do dia (candle "doji" honesto) em vez de
        # deixar nulo.
        def _val(col: str) -> float:
            v = row.get(col)
            if _is_missing(v) or float(v) == 0:
                return close
            return float(v)
        open_, high_, low_ = _val("Open"), _val("High"), _val("Low")
        rows.append({
            "ticker": ticker, "date": d,
            "open":   open_,
            "high":   high_,
            "low":    low_,
            "close":  close,
            "volume": float(row.get("Volume",0) or 0) or None,
            "adj_close": close,
        })
    return rows

def update_prices(tickers: Optional[list[str]] = None) -> dict[str, int]:
    """Download incremental para todos (ou subset) dos ativos. Retorna {ticker: rows}."""
    if tickers is None:
        with get_session() as s:
            tickers = AssetRepository(s).get_active_tickers()
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

    ok  = sum(1 for v in results.values() if v >= 0)
    tot = sum(v for v in results.values() if v > 0)
    logger.success(f"Download: {ok}/{len(tickers)} ativos OK | {tot} novos precos")
    return results