"""
Universo expandido do RRGCOMPLETO: união do IBOV + TODOS os membros de
qualquer sub-índice setorial B3 (IFNC, IEEX, IMOB, ICON, IMAT, UTIL, SMLL,
INDX, IDIV, IBLV) — não só os ~78 do IBOV, ~155 tickers ao todo.

Precisa que sync_sector_components() (app/downloader/sector_components.py)
já tenha rodado antes — é de lá que vem a composição completa de cada
sub-índice. sync_universe() só faz a união e grava em Asset.
"""
from __future__ import annotations

from app.database.connection import get_session
from app.database.repository import AssetRepository, SectorComponentRepository
from app.downloader.ibov_components import fetch_ibov_components
from app.downloader.sector_components import SECTOR_CODES, CURATED_CODES
from app.utils.logger import logger


def sync_universe() -> int:
    ibov = fetch_ibov_components()  # [{"ticker","name","weight"}, ...]
    ibov_by_ticker = {c["ticker"]: c for c in ibov}

    with get_session() as s:
        scr = SectorComponentRepository(s)
        sector_tickers: set[str] = set()
        for code in SECTOR_CODES + CURATED_CODES:
            sector_tickers |= set(scr.get_tickers(code))

    universe = set(ibov_by_ticker) | sector_tickers

    with get_session() as s:
        repo = AssetRepository(s)
        repo.deactivate_all()
        for ticker in sorted(universe):
            info = ibov_by_ticker.get(ticker)
            repo.upsert(
                ticker=ticker,
                name=(info or {}).get("name", ""),
                weight=(info or {}).get("weight", 0.0),
                is_ibov=info is not None,
            )

    n_ibov = len(ibov_by_ticker)
    logger.success(
        f"Universo RRGCOMPLETO sincronizado: {len(universe)} ativos "
        f"({n_ibov} no IBOV, {len(universe) - n_ibov} fora do IBOV)"
    )
    return len(universe)
