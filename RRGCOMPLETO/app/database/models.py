"""
Modelos SQLAlchemy.

RRGCOMPLETO — variante do RRG_Dashboard com universo expandido: não só os
78 componentes do IBOVESPA, mas TODOS os tickers que aparecem em qualquer
sub-índice setorial B3 (~155 ativos). Ver app/downloader/universe.py.

Tabelas:
    assets           — universo completo (ticker, nome, peso no IBOV se houver, is_ibov)
    sector_components — membership de cada ticker nos sub-índices B3 (proxy de setor)
    prices           — histórico OHLCV diário (inclui o próprio IBOV, ticker="IBOV")
    weekly_metrics   — RS-Ratio / RS-Momentum / quadrante / score, por ticker e semana
"""
from datetime import date, datetime
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Asset(Base):
    """Ativo do universo completo (IBOV + membros de qualquer sub-índice setorial)."""

    __tablename__ = "assets"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticker: str = Column(String(10), unique=True, nullable=False, index=True)
    name: str = Column(String(120), nullable=True)
    weight: float = Column(Float, nullable=True)  # participação no IBOV (%) — 0 se não é do IBOV
    is_ibov: bool = Column(Boolean, default=False, nullable=False)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(DateTime, server_default=func.now())
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Asset {self.ticker}>"


class SectorComponent(Base):
    """Membership de um ticker num sub-índice setorial B3 (IFNC, IMOB, ICON, IMAT, UTIL, SMLL, INDX, IEEX)."""

    __tablename__ = "sector_components"
    __table_args__ = (UniqueConstraint("sector_code", "ticker", name="uq_sector_comp"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    sector_code: str = Column(String(10), nullable=False, index=True)
    ticker: str = Column(String(10), nullable=False, index=True)


class Price(Base):
    """Preço OHLCV diário. ticker="IBOV" guarda o índice em si (^BVSP)."""

    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_price_ticker_date"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticker: str = Column(String(10), nullable=False, index=True)
    date: date = Column(Date, nullable=False, index=True)
    open: float = Column(Float, nullable=True)
    high: float = Column(Float, nullable=True)
    low: float = Column(Float, nullable=True)
    close: float = Column(Float, nullable=False)
    volume: float = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Price {self.ticker} {self.date}>"


class WeeklyMetric(Base):
    """RS-Ratio / RS-Momentum / quadrante / score de um ticker numa semana."""

    __tablename__ = "weekly_metrics"
    __table_args__ = (UniqueConstraint("ticker", "week_ending", name="uq_weekly_ticker_week"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticker: str = Column(String(10), nullable=False, index=True)
    week_ending: date = Column(Date, nullable=False, index=True)
    close: float = Column(Float, nullable=True)
    weekly_return: float = Column(Float, nullable=True)       # retorno da ação na semana (%)
    ibov_weekly_return: float = Column(Float, nullable=True)  # retorno do IBOV na semana (%)
    rs_ratio: float = Column(Float, nullable=True)
    rs_momentum: float = Column(Float, nullable=True)
    quadrant: str = Column(String(12), nullable=True)   # Leading / Improving / Weakening / Lagging
    rotation_score: float = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<WeeklyMetric {self.ticker} {self.week_ending} {self.quadrant}>"


class DailyMetric(Base):
    """Versao diaria do WeeklyMetric (15/jul/2026) — mesma metodologia RRG,
    calculada direto sobre o close diario (sem resample), janela
    RS_RATIO_SMA_DAYS/RS_MOMENTUM_SMA_DAYS em vez de semanas."""

    __tablename__ = "daily_metrics"
    __table_args__ = (UniqueConstraint("ticker", "ref_date", name="uq_daily_ticker_date"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticker: str = Column(String(10), nullable=False, index=True)
    ref_date: date = Column(Date, nullable=False, index=True)
    close: float = Column(Float, nullable=True)
    daily_return: float = Column(Float, nullable=True)       # retorno da ação no dia (%)
    ibov_daily_return: float = Column(Float, nullable=True)  # retorno do IBOV no dia (%)
    rs_ratio: float = Column(Float, nullable=True)
    rs_momentum: float = Column(Float, nullable=True)
    quadrant: str = Column(String(12), nullable=True)   # Leading / Improving / Weakening / Lagging
    rotation_score: float = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<DailyMetric {self.ticker} {self.ref_date} {self.quadrant}>"
