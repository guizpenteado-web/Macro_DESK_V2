"""
Repository Pattern — acesso padronizado ao banco de dados.
"""
from datetime import date
from typing import Optional

from sqlalchemy import select, delete
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database.models import Asset, Price, SectorComponent, WeeklyMetric


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def upsert(self, ticker: str, name: str = "", weight: float = 0.0, is_ibov: bool = False) -> None:
        stmt = sqlite_insert(Asset).values(ticker=ticker, name=name, weight=weight, is_ibov=is_ibov)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={"name": name, "weight": weight, "is_ibov": is_ibov, "is_active": True},
        )
        self._s.execute(stmt)

    def get_active_tickers(self) -> list[str]:
        rows = self._s.execute(select(Asset.ticker).where(Asset.is_active == True)).scalars().all()
        return list(rows)

    def get_all(self) -> list[Asset]:
        return list(self._s.execute(select(Asset).where(Asset.is_active == True)).scalars().all())

    def deactivate_all(self) -> None:
        from sqlalchemy import update
        self._s.execute(update(Asset).values(is_active=False))


class SectorComponentRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def replace_sector(self, sector_code: str, tickers: list[str]) -> None:
        self._s.execute(delete(SectorComponent).where(SectorComponent.sector_code == sector_code))
        for t in tickers:
            self._s.add(SectorComponent(sector_code=sector_code, ticker=t))

    def get_sectors_by_ticker(self) -> dict[str, list[str]]:
        """{ticker: [sector_code, ...]}"""
        rows = self._s.execute(select(SectorComponent.ticker, SectorComponent.sector_code)).all()
        out: dict[str, list[str]] = {}
        for ticker, code in rows:
            out.setdefault(ticker, []).append(code)
        return out

    def get_tickers(self, sector_code: str) -> list[str]:
        return list(self._s.execute(
            select(SectorComponent.ticker).where(SectorComponent.sector_code == sector_code)
        ).scalars().all())


class PriceRepository:
    def __init__(self, session: Session) -> None:
        self._s = session

    def bulk_upsert(self, rows: list[dict]) -> int:
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
            },
        )
        self._s.execute(stmt)
        return len(rows)

    def get_latest_date(self, ticker: str) -> Optional[date]:
        return self._s.execute(
            select(Price.date).where(Price.ticker == ticker).order_by(Price.date.desc()).limit(1)
        ).scalar_one_or_none()

    def get_history(self, ticker: str) -> list[Price]:
        return list(self._s.execute(
            select(Price).where(Price.ticker == ticker).order_by(Price.date.asc())
        ).scalars().all())

    def get_recent(self, ticker: str, n_days: int = 20) -> list[Price]:
        rows = list(self._s.execute(
            select(Price).where(Price.ticker == ticker).order_by(Price.date.desc()).limit(n_days)
        ).scalars().all())
        return list(reversed(rows))


class WeeklyMetricRepository:
    # SQLite tem um limite de variaveis por statement (tipicamente 999-32766) —
    # com 9 colunas por linha, 400 linhas/lote fica bem abaixo de qualquer limite.
    _CHUNK_SIZE = 400

    def __init__(self, session: Session) -> None:
        self._s = session

    def bulk_upsert(self, rows: list[dict]) -> int:
        if not rows:
            return 0
        for i in range(0, len(rows), self._CHUNK_SIZE):
            chunk = rows[i:i + self._CHUNK_SIZE]
            stmt = sqlite_insert(WeeklyMetric).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=["ticker", "week_ending"],
                set_={k: getattr(stmt.excluded, k) for k in (
                    "close", "weekly_return", "ibov_weekly_return",
                    "rs_ratio", "rs_momentum", "quadrant", "rotation_score",
                )},
            )
            self._s.execute(stmt)
        return len(rows)

    def get_all(self) -> list[WeeklyMetric]:
        return list(self._s.execute(
            select(WeeklyMetric).order_by(WeeklyMetric.ticker, WeeklyMetric.week_ending)
        ).scalars().all())
