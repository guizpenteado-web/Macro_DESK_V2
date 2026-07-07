"""
Repository Pattern — acesso padronizado ao banco de dados.
Cada repositório encapsula as queries de uma entidade.
"""
from datetime import date
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.models import Asset, Breadth, Indicator, Price, IndexComponent, IndexBreadth


class AssetRepository:
    """CRUD para a tabela assets."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, ticker: str, name: str = "", sector: str = "", weight: float = 0.0) -> None:
        stmt = sqlite_insert(Asset).values(ticker=ticker, name=name, sector=sector, weight=weight)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={"name": name, "sector": sector, "weight": weight, "is_active": True},
        )
        self._s.execute(stmt)

    def get_active_tickers(self) -> list[str]:
        rows = self._s.execute(select(Asset.ticker).where(Asset.is_active == True)).scalars().all()
        return list(rows)

    def deactivate_all(self) -> None:
        from sqlalchemy import update
        self._s.execute(update(Asset).values(is_active=False))

    def count(self) -> int:
        return self._s.execute(select(Asset).where(Asset.is_active == True)).scalars().__length_hint__()


class PriceRepository:
    """CRUD para a tabela prices."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def bulk_upsert(self, rows: list[dict]) -> int:
        """Insere ou substitui registros. Retorna quantidade processada."""
        if not rows:
            return 0
        stmt = sqlite_insert(Price).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={
                "open": stmt.excluded.open,
                "high": stmt.excluded.high,
                "low": stmt.excluded.low,
                "close": stmt.excluded.close,
                "volume": stmt.excluded.volume,
                "adj_close": stmt.excluded.adj_close,
            },
        )
        self._s.execute(stmt)
        return len(rows)

    def get_latest_date(self, ticker: str) -> Optional[date]:
        row = self._s.execute(
            select(Price.date).where(Price.ticker == ticker).order_by(Price.date.desc()).limit(1)
        ).scalar_one_or_none()
        return row


class IndicatorRepository:
    """CRUD para a tabela indicators."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        stmt = sqlite_insert(Indicator).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker", "date"],
            set_={k: getattr(stmt.excluded, k) for k in (
                "close", "sma21", "sma50", "sma200",
                "above_sma21", "above_sma50", "above_sma200",
                "rsi14", "above_rsi70", "below_rsi30",
            )},
        )
        self._s.execute(stmt)
        return len(rows)

    def get_latest(self, ticker: str) -> Optional[Indicator]:
        return self._s.execute(
            select(Indicator).where(Indicator.ticker == ticker).order_by(Indicator.date.desc()).limit(1)
        ).scalar_one_or_none()


class BreadthRepository:
    """CRUD para a tabela breadth."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, row: dict) -> None:
        stmt = sqlite_insert(Breadth).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["date"],
            set_={k: v for k, v in row.items() if k != "date"},
        )
        self._s.execute(stmt)

    def get_history(self, limit: int = 252) -> list[Breadth]:
        return list(
            self._s.execute(
                select(Breadth).order_by(Breadth.date.desc()).limit(limit)
            ).scalars().all()
        )

    def get_latest(self) -> Optional[Breadth]:
        return self._s.execute(
            select(Breadth).order_by(Breadth.date.desc()).limit(1)
        ).scalar_one_or_none()


class IndexComponentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def replace_index(self, index_code: str, rows: list[dict]) -> None:
        self._s.execute(
            delete(IndexComponent).where(IndexComponent.index_code == index_code)
        )
        for r in rows:
            self._s.add(IndexComponent(**r))

    def get_tickers(self, index_code: str) -> list[str]:
        return list(self._s.execute(
            select(IndexComponent.ticker).where(IndexComponent.index_code == index_code)
        ).scalars().all())

    def get_all_tickers(self) -> list[str]:
        return list(self._s.execute(
            select(IndexComponent.ticker).distinct()
        ).scalars().all())


class IndexBreadthRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, row: dict) -> None:
        stmt = sqlite_insert(IndexBreadth).values(**row)
        stmt = stmt.on_conflict_do_update(
            index_elements=["index_code", "date"],
            set_={k: v for k, v in row.items() if k not in ("index_code", "date")},
        )
        self._s.execute(stmt)
