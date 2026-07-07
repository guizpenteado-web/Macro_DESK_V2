import sqlite3
from contextlib import contextmanager
from app.settings import DATABASE_PATH


def init_db():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _conn() as con:
        con.executescript("""
            CREATE TABLE IF NOT EXISTS macro_data (
                series_id TEXT NOT NULL,
                date      TEXT NOT NULL,
                value     REAL,
                PRIMARY KEY (series_id, date)
            );
            CREATE TABLE IF NOT EXISTS prices (
                ticker TEXT NOT NULL,
                date   TEXT NOT NULL,
                close  REAL NOT NULL,
                PRIMARY KEY (ticker, date)
            );
            CREATE TABLE IF NOT EXISTS cot_data (
                contract TEXT NOT NULL,
                date     TEXT NOT NULL,
                mm_net   REAL,
                am_net   REAL,
                oi       REAL,
                PRIMARY KEY (contract, date)
            );
        """)


@contextmanager
def _conn():
    con = sqlite3.connect(str(DATABASE_PATH))
    con.execute("PRAGMA journal_mode=WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def upsert_macro(series_id: str, rows: list[tuple]):
    """rows: list of (date_str, value)"""
    with _conn() as con:
        con.executemany(
            "INSERT OR REPLACE INTO macro_data (series_id, date, value) VALUES (?,?,?)",
            [(series_id, d, v) for d, v in rows],
        )


def upsert_prices(ticker: str, rows: list[tuple]):
    """rows: list of (date_str, close)"""
    with _conn() as con:
        con.executemany(
            "INSERT OR REPLACE INTO prices (ticker, date, close) VALUES (?,?,?)",
            [(ticker, d, c) for d, c in rows],
        )


def get_macro(series_id: str) -> list[tuple]:
    """Returns list of (date, value) sorted by date"""
    with _conn() as con:
        cur = con.execute(
            "SELECT date, value FROM macro_data WHERE series_id=? ORDER BY date",
            (series_id,),
        )
        return cur.fetchall()


def get_prices(ticker: str) -> list[tuple]:
    """Returns list of (date, close) sorted by date"""
    with _conn() as con:
        cur = con.execute(
            "SELECT date, close FROM prices WHERE ticker=? ORDER BY date",
            (ticker,),
        )
        return cur.fetchall()


def last_macro_date(series_id: str) -> str | None:
    with _conn() as con:
        cur = con.execute(
            "SELECT MAX(date) FROM macro_data WHERE series_id=?", (series_id,)
        )
        row = cur.fetchone()
        return row[0] if row else None


def last_price_date(ticker: str) -> str | None:
    with _conn() as con:
        cur = con.execute(
            "SELECT MAX(date) FROM prices WHERE ticker=?", (ticker,)
        )
        row = cur.fetchone()
        return row[0] if row else None


def upsert_cot(rows: list[tuple]):
    """rows: list of (contract, date, mm_net, am_net, oi)"""
    with _conn() as con:
        con.executemany(
            "INSERT OR REPLACE INTO cot_data (contract, date, mm_net, am_net, oi) VALUES (?,?,?,?,?)",
            rows,
        )


def get_cot(contract: str) -> list[tuple]:
    """Returns list of (date, mm_net, am_net, oi) sorted by date"""
    with _conn() as con:
        cur = con.execute(
            "SELECT date, mm_net, am_net, oi FROM cot_data WHERE contract=? ORDER BY date",
            (contract,),
        )
        return cur.fetchall()
