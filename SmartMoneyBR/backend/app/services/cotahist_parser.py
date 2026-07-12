"""Parser for B3's COTAHIST fixed-width layout (registro tipo 01).

Field positions verified 12/jul/2026 against real downloaded data
(COTAHIST_D10072026.ZIP) by cross-checking parsed PETR4/VALE3/ITUB4/ASAI3
values — PETR4 2026-07-10 open=39.64/close=39.65 matched brapi.dev exactly
for the same date, confirming the layout below is correct, not guessed
from a spec.

CODBDI='02' (Lote Padrao — the regular round-lot market for common/
preferred shares) + TPMERC='010' (mercado a vista/spot) together select
exactly one row per ticker per trading day: the ordinary equity price,
excluding FIIs (CODBDI 12), BDRs (14), options, forwards, and the
fractional-lot market. Confirmed zero (ticker, date) collisions across a
full day's file (324 tickers, 324 rows) with this filter.
"""
from __future__ import annotations

import zipfile
from datetime import date
from pathlib import Path

EQUITY_CODBDI = "02"
SPOT_TPMERC = "010"


def _parse_line(line: str) -> dict | None:
    if len(line) < 200 or line[0:2] != "01":
        return None
    if line[10:12] != EQUITY_CODBDI or line[24:27] != SPOT_TPMERC:
        return None

    ticker = line[12:24].strip()
    d = line[2:10]  # YYYYMMDD
    return {
        "ticker": ticker,
        "trade_date": date(int(d[0:4]), int(d[4:6]), int(d[6:8])),
        "open": int(line[56:69]) / 100,
        "high": int(line[69:82]) / 100,
        "low": int(line[82:95]) / 100,
        "close": int(line[108:121]) / 100,
        "volume": int(line[170:188]) / 100,
    }


def parse_cotahist_zip(zip_path: Path) -> list[dict]:
    """Returns every equity ticker's daily OHLC for the whole file (a full
    year, for the annual bundles) — not filtered to one ticker, so the
    caller can cache all of it at once and serve any ticker from that year
    without re-downloading."""
    with zipfile.ZipFile(zip_path) as zf:
        member = next(n for n in zf.namelist() if n.upper().endswith(".TXT"))
        raw = zf.read(member)

    rows = []
    for raw_line in raw.split(b"\n"):
        line = raw_line.decode("latin-1").rstrip("\r")
        parsed = _parse_line(line)
        if parsed:
            rows.append(parsed)
    return rows
