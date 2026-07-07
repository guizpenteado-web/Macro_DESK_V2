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
    @event.listens_for(engine, "connect")
    def set_pragmas(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_db_engine() -> Engine:
    db_url = f"sqlite:///{settings.database_path}"
    engine = create_engine(db_url, echo=False, future=True)
    _configure_sqlite(engine)
    return engine


engine: Engine = create_db_engine()
SessionFactory: sessionmaker = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def init_database() -> None:
    Base.metadata.create_all(bind=engine)


@contextmanager
def get_session() -> Generator[Session, None, None]:
    session: Session = SessionFactory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
