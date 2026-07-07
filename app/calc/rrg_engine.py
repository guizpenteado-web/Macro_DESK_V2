"""
Motor de cálculo do RRG (Relative Rotation Graph) — sempre ação vs IBOV.

Metodologia (constantes em app/config/settings.py):
    RelPrice(t)    = Close_ação(t) / Close_IBOV(t)
    RS_Ratio(t)    = 100 * RelPrice(t) / SMA(RelPrice, RS_RATIO_SMA_WEEKS)(t)
    RS_Momentum(t) = 100 * RS_Ratio(t) / SMA(RS_Ratio, RS_MOMENTUM_SMA_WEEKS)(t)

Os dois osciladores giram em torno de 100 — exatamente a convenção clássica
do RRG (eixos do quadrante em RS_Ratio=100 / RS_Momentum=100).
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from app.config.settings import settings
from app.database.connection import get_session
from app.database.repository import AssetRepository, PriceRepository, WeeklyMetricRepository
from app.downloader.price_downloader import IBOV_TICKER
from app.utils.logger import logger


def _weekly_close(ticker: str) -> pd.Series:
    with get_session() as s:
        prices = PriceRepository(s).get_history(ticker)
    if not prices:
        return pd.Series(dtype=float)
    df = pd.DataFrame([{"date": p.date, "close": p.close} for p in prices])
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    weekly = df["close"].resample("W-FRI").last().dropna()
    # A semana corrente (ainda em andamento) cai num bucket rotulado com a
    # sexta-feira futura — descarta pra não misturar 1-2 dias parciais como
    # se fosse a semana fechada.
    today = pd.Timestamp(date.today())
    return weekly[weekly.index <= today]


def _quadrant(rs_ratio: float, rs_momentum: float) -> str:
    if rs_ratio >= 100 and rs_momentum >= 100:
        return "Leading"
    if rs_ratio >= 100 and rs_momentum < 100:
        return "Weakening"
    if rs_ratio < 100 and rs_momentum >= 100:
        return "Improving"
    return "Lagging"


def _rotation_score(rs_ratio: float, rs_momentum: float, quadrant: str, streak_weeks: int) -> float:
    dev_rs = max(-settings.SCORE_RS_CLAMP, min(settings.SCORE_RS_CLAMP, rs_ratio - 100))
    dev_mom = max(-settings.SCORE_MOM_CLAMP, min(settings.SCORE_MOM_CLAMP, rs_momentum - 100))
    persistence = min(streak_weeks, settings.SCORE_PERSISTENCE_CAP_WEEKS) * settings.SCORE_PERSISTENCE_PER_WEEK
    if quadrant == "Leading":
        persistence_adj = persistence
    elif quadrant == "Lagging":
        persistence_adj = -persistence
    else:
        persistence_adj = 0.0
    score = (
        settings.SCORE_BASE
        + settings.SCORE_RS_WEIGHT * dev_rs
        + settings.SCORE_MOM_WEIGHT * dev_mom
        + persistence_adj
    )
    return max(0.0, min(100.0, score))


def compute_ticker_metrics(ticker: str, ibov_weekly: pd.Series) -> list[dict]:
    weekly = _weekly_close(ticker)
    if weekly.empty:
        return []

    aligned = pd.concat([weekly.rename("close"), ibov_weekly.rename("ibov_close")], axis=1).dropna()
    warmup = settings.RS_RATIO_SMA_WEEKS + settings.RS_MOMENTUM_SMA_WEEKS
    if len(aligned) < warmup + 5:
        return []  # histórico insuficiente (IPO recente ou pouco dado ainda)

    rel_price = aligned["close"] / aligned["ibov_close"]
    rs_ratio = 100 * rel_price / rel_price.rolling(settings.RS_RATIO_SMA_WEEKS).mean()
    rs_momentum = 100 * rs_ratio / rs_ratio.rolling(settings.RS_MOMENTUM_SMA_WEEKS).mean()
    weekly_return = aligned["close"].pct_change() * 100
    ibov_weekly_return = aligned["ibov_close"].pct_change() * 100

    df = pd.DataFrame({
        "close": aligned["close"],
        "weekly_return": weekly_return,
        "ibov_weekly_return": ibov_weekly_return,
        "rs_ratio": rs_ratio,
        "rs_momentum": rs_momentum,
    }).dropna()
    if df.empty:
        return []

    df["quadrant"] = [_quadrant(r, m) for r, m in zip(df["rs_ratio"], df["rs_momentum"])]

    # streak = semanas consecutivas no mesmo quadrante (persistência, pro score)
    streaks: list[int] = []
    prev_q, streak = None, 0
    for q in df["quadrant"]:
        streak = streak + 1 if q == prev_q else 1
        streaks.append(streak)
        prev_q = q
    df["_streak"] = streaks

    df["rotation_score"] = [
        _rotation_score(r, m, q, st)
        for r, m, q, st in zip(df["rs_ratio"], df["rs_momentum"], df["quadrant"], df["_streak"])
    ]

    df = df.tail(settings.MAX_WEEKS)

    return [
        {
            "ticker": ticker,
            "week_ending": week_ending.date(),
            "close": float(row["close"]),
            "weekly_return": float(row["weekly_return"]),
            "ibov_weekly_return": float(row["ibov_weekly_return"]),
            "rs_ratio": float(row["rs_ratio"]),
            "rs_momentum": float(row["rs_momentum"]),
            "quadrant": row["quadrant"],
            "rotation_score": float(row["rotation_score"]),
        }
        for week_ending, row in df.iterrows()
    ]


def compute_all() -> int:
    with get_session() as s:
        tickers = AssetRepository(s).get_active_tickers()

    ibov_weekly = _weekly_close(IBOV_TICKER)
    if ibov_weekly.empty:
        logger.error("Sem histórico do IBOV — rode o download de preços primeiro.")
        return 0

    all_rows: list[dict] = []
    n_ok = 0
    for ticker in tickers:
        rows = compute_ticker_metrics(ticker, ibov_weekly)
        if rows:
            n_ok += 1
        all_rows.extend(rows)

    with get_session() as s:
        WeeklyMetricRepository(s).bulk_upsert(all_rows)

    logger.success(f"Métricas RRG calculadas: {n_ok}/{len(tickers)} ativos, {len(all_rows)} linhas semanais")
    return len(all_rows)
