"""
Calcula sazonalidade mensal histórica a partir dos preços no SQLite.
- Para cada ativo: retorno médio por mês (Jan–Dez) nos últimos N anos.
- Para VIX: nível médio por mês (não retorno).
"""
import pandas as pd
from app.database import get_prices

MONTH_LABELS = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]


def _load_series(ticker: str) -> pd.Series:
    rows = get_prices(ticker)
    if not rows:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([r[0] for r in rows])
    vals = [r[1] for r in rows]
    return pd.Series(vals, index=idx, name=ticker).sort_index()


def calc_seasonality_returns(ticker: str, years: int = 20, outlier_pct: float = 100.0) -> dict:
    """Returns {month_label: avg_pct_return} for the last `years` years.
    outlier_pct: filtro de outlier (default 100%). NG=F usa 60% para excluir roll artifacts
    identificados no CFTC data (ex: Set/2009 +62.6% — roll artifact documentado).
    """
    s = _load_series(ticker)
    if s.empty:
        return {}
    cutoff = s.index.max() - pd.DateOffset(years=years)
    s = s[s.index >= cutoff]
    monthly = s.resample("ME").last().pct_change() * 100
    monthly = monthly.dropna()
    monthly = monthly[monthly.abs() <= outlier_pct]
    by_month = monthly.groupby(monthly.index.month).mean()
    return {MONTH_LABELS[m - 1]: round(float(by_month.get(m, 0)), 2) for m in range(1, 13)}


def calc_seasonality_level(ticker: str, years: int = 20) -> dict:
    """Returns {month_label: avg_level} — usado para VIX."""
    s = _load_series(ticker)
    if s.empty:
        return {}
    cutoff = s.index.max() - pd.DateOffset(years=years)
    s = s[s.index >= cutoff]
    monthly_avg = s.resample("ME").mean()
    by_month = monthly_avg.groupby(monthly_avg.index.month).mean()
    return {MONTH_LABELS[m - 1]: round(float(by_month.get(m, 0)), 2) for m in range(1, 13)}


def calc_btc_seasonality() -> dict:
    return calc_seasonality_returns("BTC-USD", years=12)


def calc_btc_cycle(halvings: list[dict]) -> dict:
    """
    Returns cycles dict:
    {
      "cycle_1": {"label": "2012", "x": [days...], "y": [indexed_price...]},
      ...
    }
    """
    import pandas as pd
    s = _load_series("BTC-USD")
    if s.empty:
        return {}

    cycles = {}
    for i, h in enumerate(halvings):
        h_date = pd.Timestamp(h["date"])
        next_h = pd.Timestamp(halvings[i + 1]["date"]) if i + 1 < len(halvings) else s.index.max()

        segment = s[(s.index >= h_date) & (s.index < next_h)]
        if segment.empty:
            continue

        base = float(segment.iloc[0])
        if base == 0:
            continue

        days = [(d - h_date).days for d in segment.index]
        indexed = [round(float(v) / base, 4) for v in segment.values]

        cycles[f"cycle_{i+1}"] = {
            "label": h["label"],
            "halving_date": h["date"],
            "x": days,
            "y": indexed,
        }

    return cycles


def get_cycle_stats(halvings: list[dict]) -> dict:
    """Stats for the current (most recent) cycle."""
    import pandas as pd, datetime
    s = _load_series("BTC-USD")
    if s.empty:
        return {}

    last_halving = pd.Timestamp(halvings[-1]["date"])
    segment = s[s.index >= last_halving]
    if segment.empty:
        return {}

    base = float(segment.iloc[0])
    current = float(segment.iloc[-1])
    days_since = (pd.Timestamp.now() - last_halving).days
    pct_from_halving = round((current - base) / base * 100, 1)

    ath_all = float(s.max())
    pct_from_ath = round((current - ath_all) / ath_all * 100, 1)

    return {
        "halving_date":      halvings[-1]["date"],
        "days_since_halving": days_since,
        "price_at_halving":  round(base, 2),
        "current_price":     round(current, 2),
        "pct_from_halving":  pct_from_halving,
        "all_time_high":     round(ath_all, 2),
        "pct_from_ath":      pct_from_ath,
        "last_date":         str(segment.index[-1].date()),
    }
