"""Client for B3's own historical quote files (COTAHIST) — genuinely free,
no key, no rate limit, official primary source (the exchange itself).
Unlike third-party resellers (e.g. brapi.dev, which paywalls everything
beyond 4 blue-chip tickers past a free trial), this is the same data B3
itself publishes for anyone. Yearly files cover every year since 1986;
each contains EVERY B3-listed ticker's daily OHLC for that whole year
(fixed-width text, ~245 bytes/row) — see cotahist_parser.py for the
verified field layout."""
from __future__ import annotations

import logging
from pathlib import Path

import requests

from app.config import settings

logger = logging.getLogger(__name__)

COTAHIST_URL_TEMPLATE = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{year}.ZIP"


def cotahist_zip_path(year: int) -> Path:
    return Path(settings.data_cache_dir) / "cotahist" / f"COTAHIST_A{year}.ZIP"


def download_cotahist_year(year: int, force: bool = False) -> Path:
    """Download (or reuse cached) annual COTAHIST zip. Closed years never
    get revised by B3, so the cache is trustworthy forever — force=True is
    only useful for the current (still-trading) year or a corrupted file."""
    dest = cotahist_zip_path(year)
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and not force:
        logger.info("cotahist %d: usando cache local (%s)", year, dest)
        return dest
    url = COTAHIST_URL_TEMPLATE.format(year=year)
    logger.info("cotahist %d: baixando %s", year, url)
    resp = requests.get(url, timeout=300)
    resp.raise_for_status()
    dest.write_bytes(resp.content)
    return dest
