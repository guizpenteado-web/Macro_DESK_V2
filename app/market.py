"""
Coleta preços históricos via yfinance (mercados) e FRED (spot sem roll) para sazonalidade.
"""
import time, logging
import requests
import pandas as pd
import yfinance as yf
from app.database import upsert_prices, last_price_date
from app.settings import SEASONALITY_TICKERS, BTC_TICKER, SEASONALITY_YEARS, FRED_TICKERS

log = logging.getLogger(__name__)


def _all_tickers() -> list[str]:
    tickers = []
    for group in SEASONALITY_TICKERS.values():
        tickers.extend(group.values())
    tickers.append(BTC_TICKER)
    return list(set(tickers))


def collect_ticker(ticker: str):
    last = last_price_date(ticker)
    start = last if last else f"{pd.Timestamp.now().year - SEASONALITY_YEARS}-01-01"

    try:
        df = yf.download(ticker, start=start, progress=False, auto_adjust=True, threads=False)
        if df.empty:
            log.warning("yfinance: %s retornou vazio", ticker)
            return
        close_col = "Close"
        if isinstance(df.columns, pd.MultiIndex):
            close_col = ("Close", ticker)
        rows = [
            (str(idx.date()), float(row[close_col]))
            for idx, row in df.iterrows()
            if not pd.isna(row[close_col])
        ]
        if rows:
            upsert_prices(ticker, rows)
            log.info("yfinance %s: %d registros", ticker, len(rows))
    except Exception as e:
        log.error("yfinance %s error: %s", ticker, e)


def collect_fred():
    """Coleta series do FRED via CSV e armazena como precos mensais."""
    start_year = pd.Timestamp.now().year - SEASONALITY_YEARS
    cutoff = f"{start_year}-01-01"
    for series_id, label in FRED_TICKERS.items():
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
        try:
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            rows = []
            for line in r.text.strip().split('\n')[1:]:
                parts = line.split(',')
                if len(parts) == 2 and parts[1].strip() not in ('.', ''):
                    date_str = parts[0].strip()
                    if date_str >= cutoff:
                        rows.append((date_str, float(parts[1].strip())))
            if rows:
                upsert_prices(series_id, rows)
                log.info("FRED %s (%s): %d registros", series_id, label, len(rows))
        except Exception as e:
            log.error("FRED %s error: %s", series_id, e)


def collect_all():
    fred_ids = set(FRED_TICKERS.keys())
    yf_tickers = [t for t in _all_tickers() if t not in fred_ids]
    log.info("Coletando %d tickers via yfinance...", len(yf_tickers))
    for ticker in yf_tickers:
        collect_ticker(ticker)
        time.sleep(0.3)
    collect_fred()
