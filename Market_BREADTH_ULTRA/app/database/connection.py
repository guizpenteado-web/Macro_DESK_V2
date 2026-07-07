"""
Gerenciamento de conexão com o banco SQLite via SQLAlchemy.
Fornece engine, session factory e context manager de sessão.
"""
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.config.settings import settings
from app.database.models import Base


def _configure_sqlite(engine: Engine) -> None:
    """Habilita WAL mode e foreign keys no SQLite após cada conexão."""
    @event.listens_for(engine, "connect")
    def set_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_engine() -> Engine:
    """Cria e retorna o engine SQLAlchemy configurado."""
    db_url = f"sqlite:///{settings.database_path}"
    engine = create_engine(db_url, echo=False, future=True)
    _configure_sqlite(engine)
    return engine


# Engine e SessionFactory globais
engine: Engine = create_db_engine()
SessionFactory: sessionmaker = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_database() -> None:
    """Cria todas as tabelas no banco se ainda não existirem."""
    Base.metadata.create_all(bind=engine)
    _migrate_database()


def _migrate_database() -> None:
    """Adiciona colunas novas a tabelas existentes (idempotente)."""
    from sqlalchemy import text
    new_cols = [
        ("indicators", "rsi14",           "REAL"),
        ("indicators", "above_rsi70",     "INTEGER"),
        ("indicators", "below_rsi30",     "INTEGER"),
        ("breadth",    "count_rsi_oversold",  "INTEGER"),
        ("breadth",    "count_rsi_neutral",   "INTEGER"),
        ("breadth",    "count_rsi_overbought","INTEGER"),
        ("breadth",    "pct_rsi_oversold",    "REAL"),
        ("breadth",    "pct_rsi_neutral",     "REAL"),
        ("breadth",    "pct_rsi_overbought",  "REAL"),
    ]
    with engine.connect() as conn:
        for table, col, typ in new_cols:
            try:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {col} {typ}"))
                conn.commit()
            except Exception:
                pass


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """
    Context manager que fornece uma sessão e faz commit/rollback automaticamente.

    Uso:
        with get_session() as session:
            session.add(obj)
    """
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
