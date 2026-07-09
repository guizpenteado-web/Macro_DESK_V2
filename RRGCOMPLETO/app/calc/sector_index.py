"""
Índice sintético por setor — mesma ideia do RRG_Dashboard original, mas
agora com TODOS os membros reais de cada sub-índice B3 (não só a fatia que
também está no IBOV — ver app/downloader/universe.py). Trata cada sub-índice
como um "ativo" próprio e roda a MESMA metodologia RRG (RS-Ratio/Momentum/
Quadrante/Score) dele vs IBOV.

Não é o índice oficial publicado pela B3 — é uma aproximação: um preço
composto (base 100) construído a partir dos retornos diários dos membros já
baixados. Ponderação IGUALITÁRIA entre os membros (1/n cada) — não existe
fonte confiável de peso/market cap pra quem está fora do IBOV, então usar o
peso IBOV só pros membros que o têm (e ignorar o resto) sub-representaria o
setor de verdade. Guardado no ticker "SECT_<CODIGO>" na mesma tabela Price,
pra poder reaproveitar compute_ticker_metrics() sem duplicar lógica — o
prefixo deixa óbvio, olhando o banco, que é dado derivado e não uma cotação
real.
"""
from __future__ import annotations

import pandas as pd

from app.database.connection import get_session
from app.database.repository import (
    PriceRepository, SectorComponentRepository, WeeklyMetricRepository,
)
from app.downloader.price_downloader import IBOV_TICKER
from app.downloader.sector_components import SECTOR_CODES, CURATED_CODES

ALL_SECTOR_CODES = SECTOR_CODES + CURATED_CODES
from app.utils.logger import logger

SECTOR_TICKER_PREFIX = "SECT_"
MIN_MEMBERS = 3


def sector_ticker(code: str) -> str:
    return f"{SECTOR_TICKER_PREFIX}{code}"


def _build_composite(weights: dict[str, float]) -> pd.Series:
    frames: dict[str, pd.Series] = {}
    with get_session() as s:
        repo = PriceRepository(s)
        for ticker in weights:
            hist = repo.get_history(ticker)
            if hist:
                frames[ticker] = pd.Series({p.date: p.close for p in hist})

    if not frames:
        return pd.Series(dtype=float)

    prices = pd.DataFrame(frames).sort_index()
    returns = prices.pct_change()

    w = pd.Series(weights)
    w = w[w.index.isin(returns.columns)]
    if w.sum() <= 0:
        return pd.Series(dtype=float)
    w = w / w.sum()

    mask = returns.notna()
    weighted_sum = returns.mul(w, axis=1).sum(axis=1, skipna=True)
    weight_available = mask.mul(w, axis=1).sum(axis=1)
    daily_return = (weighted_sum / weight_available).fillna(0.0)
    if len(daily_return):
        daily_return.iloc[0] = 0.0  # primeira linha do pct_change é sempre NaN

    composite = 100 * (1 + daily_return).cumprod()
    composite.index = pd.to_datetime(composite.index)
    return composite


def build_all_sector_composites() -> dict[str, int]:
    totals: dict[str, int] = {}
    for code in ALL_SECTOR_CODES:
        with get_session() as s:
            members = SectorComponentRepository(s).get_tickers(code)

        if len(members) < MIN_MEMBERS:
            logger.warning(f"Setor {code}: só {len(members)} membro(s) — pulando índice sintético")
            totals[code] = 0
            continue

        weights = {t: 1.0 for t in members}  # ponderação igualitária (ver docstring do módulo)
        composite = _build_composite(weights)
        if composite.empty:
            totals[code] = 0
            continue

        rows = [
            {
                "ticker": sector_ticker(code), "date": d.date(),
                "open": None, "high": None, "low": None,
                "close": float(v), "volume": None,
            }
            for d, v in composite.items()
        ]
        with get_session() as s:
            n = PriceRepository(s).bulk_upsert(rows)
        totals[code] = n
        logger.info(f"Setor {code}: índice sintético com {n} pregões ({len(members)} membros, peso igual)")

    logger.success(f"Índices sintéticos de setor construídos: {totals}")
    return totals


def compute_sector_metrics() -> int:
    from app.calc.rrg_engine import compute_ticker_metrics, _weekly_close

    ibov_weekly = _weekly_close(IBOV_TICKER)
    if ibov_weekly.empty:
        logger.error("Sem histórico do IBOV — não dá pra calcular RRG dos setores.")
        return 0

    all_rows: list[dict] = []
    for code in ALL_SECTOR_CODES:
        all_rows.extend(compute_ticker_metrics(sector_ticker(code), ibov_weekly))

    with get_session() as s:
        WeeklyMetricRepository(s).bulk_upsert(all_rows)

    logger.success(f"Métricas RRG de setor calculadas: {len(all_rows)} linhas semanais")
    return len(all_rows)
