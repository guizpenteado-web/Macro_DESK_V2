"""Schema do banco de autenticacao do Hub — SQLite proprio, independente do
Postgres do SmartMoneyBR ou do MySQL do Trading Dashboard (login e uma
preocupacao do Hub, nao deveria depender de nenhum sub-projeto especifico).
Mesma filosofia da Biblioteca (SQLite proprio em auth/, nao no root)."""
from pathlib import Path
import sqlite3

AUTH_DIR = Path(__file__).resolve().parent
DB_PATH = AUTH_DIR / "hub_users.db"

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    nome TEXT,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')) DEFAULT 'user',
    ativo INTEGER NOT NULL DEFAULT 1,
    criado_em TEXT NOT NULL DEFAULT (datetime('now')),
    ultimo_login TEXT
);
"""


def init_db() -> None:
    AUTH_DIR.mkdir(exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    init_db()
    print(f"Banco inicializado em {DB_PATH}")
