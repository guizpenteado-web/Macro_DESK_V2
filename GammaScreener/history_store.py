"""Historico de Gamma Flip por ativo, persistido em SQLite local.

Um ponto por (ticker, data de referencia do OI). Preenchido por dois
caminhos: `backfill_history.py` (rodado uma vez, reconstroi ~12 meses pra
tras usando arquivos historicos reais da B3) e o warmer em background do
`server.py` (adiciona o ponto do dia atual, sempre que a data de
referencia do OI mudar -- assim o historico cresce sozinho dia apos dia,
sem precisar rodar o backfill de novo).
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "gamma_flip_history.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS gamma_flip_history (
    ticker      TEXT NOT NULL,
    root        TEXT NOT NULL,
    ref_date    TEXT NOT NULL,   -- YYYY-MM-DD, data do OI usado (nao a data em que foi calculado)
    gamma_flip  REAL,
    spot        REAL,
    regime      TEXT,
    iv_source   TEXT NOT NULL,   -- 'oplab_live' (dado real do dia) ou 'realized_vol_proxy' (backfill historico)
    computed_at TEXT NOT NULL,
    PRIMARY KEY (ticker, ref_date)
);
"""


def _conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(_SCHEMA)
    return conn


def upsert_snapshot(ticker, root, ref_date, gamma_flip, spot, regime, iv_source, computed_at):
    with _conn() as conn:
        conn.execute(
            "INSERT INTO gamma_flip_history "
            "(ticker, root, ref_date, gamma_flip, spot, regime, iv_source, computed_at) "
            "VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(ticker, ref_date) DO UPDATE SET "
            "gamma_flip=excluded.gamma_flip, spot=excluded.spot, regime=excluded.regime, "
            "iv_source=excluded.iv_source, computed_at=excluded.computed_at",
            (ticker, root, ref_date, gamma_flip, spot, regime, iv_source, computed_at),
        )


def get_history(ticker, months_back=12):
    with _conn() as conn:
        rows = conn.execute(
            "SELECT ref_date, gamma_flip, spot, regime, iv_source FROM gamma_flip_history "
            "WHERE ticker = ? ORDER BY ref_date ASC",
            (ticker,),
        ).fetchall()
    return [
        {"ref_date": r[0], "gamma_flip": r[1], "spot": r[2], "regime": r[3], "iv_source": r[4]}
        for r in rows
    ]


def has_snapshot(ticker, ref_date):
    with _conn() as conn:
        row = conn.execute(
            "SELECT 1 FROM gamma_flip_history WHERE ticker = ? AND ref_date = ?",
            (ticker, ref_date),
        ).fetchone()
    return row is not None
