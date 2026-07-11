"""Real investment return from a fund's quota-value series.

Naively dividing last/first quota_value produces absurd numbers for some
funds (seen in practice: +1.309.044% over 20 years) because a handful of
funds — almost always "fundos exclusivos" with 1-2 cotistas — have quota
value discontinuities that are not real market return: restructurings,
incorporations, or quota amortization events that rebase the quota value.
Confirmed on real data (fund_id 1720, 2245): single-month jumps of 2-2.6x
that don't correspond to any plausible organic monthly return.

A real fund essentially never doubles (or halves) its quota value from pure
market performance in a single month — that would require absurd leverage.
So a single-month ratio outside [0.5, 2.0] is treated as a rebase event, and
the return is computed only from the most recent such event onward (if any
fall inside the requested window), not from the raw window start.
"""
from __future__ import annotations

from datetime import date

REBASE_RATIO_HIGH = 2.0
REBASE_RATIO_LOW = 0.5


def compute_window_return(
    series: list[tuple[date, float]], window_start: date
) -> tuple[float | None, date | None]:
    """series: (ref_date, quota_value) pairs for ONE fund, sorted ascending,
    covering at least [window_start, ...]. Returns (pct_return, effective_first_date),
    both None if there isn't enough data in the window to compute a return."""
    in_window = [(d, v) for d, v in series if d >= window_start]
    if len(in_window) < 2:
        return None, None

    effective_start_idx = 0
    for i in range(1, len(in_window)):
        prev_v = in_window[i - 1][1]
        cur_v = in_window[i][1]
        if prev_v <= 0:
            continue
        ratio = cur_v / prev_v
        if ratio > REBASE_RATIO_HIGH or ratio < REBASE_RATIO_LOW:
            effective_start_idx = i  # anchor AFTER the rebase, discard the polluted prefix

    clean = in_window[effective_start_idx:]
    if len(clean) < 2:
        return None, None

    first_date, first_value = clean[0]
    last_date, last_value = clean[-1]
    if first_value <= 0:
        return None, None

    pct_return = (last_value / first_value - 1) * 100
    return pct_return, first_date
