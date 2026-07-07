"""
Modelos SQLAlchemy — mapeamento objeto-relacional das tabelas do banco.

Tabelas:
    assets     — componentes do IBOVESPA
    prices     — histórico OHLCV diário
    indicators — SMAs calculadas por ativo/data
    breadth    — resumo diário de market breadth do índice
"""
from datetime import date, datetime
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float,
    Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base para todos os modelos."""
    pass


class Asset(Base):
    """Componente do IBOVESPA."""

    __tablename__ = "assets"

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticker: str = Column(String(10), unique=True, nullable=False, index=True)
    name: str = Column(String(120), nullable=True)
    sector: str = Column(String(80), nullable=True)
    weight: float = Column(Float, nullable=True)
    is_active: bool = Column(Boolean, default=True, nullable=False)
    created_at: datetime = Column(DateTime, server_default=func.now())
    updated_at: datetime = Column(DateTime, server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Asset {self.ticker}>"


class Price(Base):
    """Preço OHLCV diário de um ativo."""

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
    adj_close: float = Column(Float, nullable=True)

    def __repr__(self) -> str:
        return f"<Price {self.ticker} {self.date}>"


class Indicator(Base):
    """Indicadores técnicos calculados por ativo e data."""

    __tablename__ = "indicators"
    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ind_ticker_date"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    ticker: str = Column(String(10), nullable=False, index=True)
    date: date = Column(Date, nullable=False, index=True)
    close: float = Column(Float, nullable=True)
    sma21: float = Column(Float, nullable=True)
    sma50: float = Column(Float, nullable=True)
    sma200: float = Column(Float, nullable=True)
    above_sma21: bool = Column(Boolean, nullable=True)
    above_sma50: bool = Column(Boolean, nullable=True)
    above_sma200: bool = Column(Boolean, nullable=True)
    rsi14: float = Column(Float, nullable=True)
    above_rsi70: bool = Column(Boolean, nullable=True)
    below_rsi30: bool = Column(Boolean, nullable=True)

    def __repr__(self) -> str:
        return f"<Indicator {self.ticker} {self.date}>"


class Breadth(Base):
    """Market Breadth diário do IBOVESPA."""

    __tablename__ = "breadth"
    __table_args__ = (UniqueConstraint("date", name="uq_breadth_date"),)

    id: int = Column(Integer, primary_key=True, autoincrement=True)
    date: date = Column(Date, nullable=False, index=True)
    total_assets: int = Column(Integer, nullable=False)
    above_sma21: int = Column(Integer, nullable=False, default=0)
    above_sma50: int = Column(Integer, nullable=False, default=0)
    above_sma200: int = Column(Integer, nullable=False, default=0)
    pct_sma21: float = Column(Float, nullable=False, default=0.0)
    pct_sma50: float = Column(Float, nullable=False, default=0.0)
    pct_sma200: float = Column(Float, nullable=False, default=0.0)
    count_rsi_oversold: int = Column(Integer, nullable=True, default=0)
    count_rsi_neutral: int = Column(Integer, nullable=True, default=0)
    count_rsi_overbought: int = Column(Integer, nullable=True, default=0)
    pct_rsi_oversold: float = Column(Float, nullable=True, default=0.0)
    pct_rsi_neutral: float = Column(Float, nullable=True, default=0.0)
    pct_rsi_overbought: float = Column(Float, nullable=True, default=0.0)
    created_at: datetime = Column(DateTime, server_default=func.now())

    def __repr__(self) -> str:
        return f"<Breadth {self.date} SMA21={self.pct_sma21:.1f}%>"


class IndexComponent(Base):
    """Componente de um sub-indice (IDIV, IFNC, EWZ, IBLV)."""

    __tablename__ = "index_components"
    __table_args__ = (UniqueConstraint("index_code", "ticker", name="uq_idx_comp"),)

    id: int         = Column(Integer, primary_key=True, autoincrement=True)
    index_code: str = Column(String(10), nullable=False, index=True)
    ticker: str     = Column(String(10), nullable=False)
    weight: float   = Column(Float, nullable=True, default=0.0)


class IndexBreadth(Base):
    """Market Breadth diario por sub-indice."""

    __tablename__ = "index_breadth"
    __table_args__ = (UniqueConstraint("index_code", "date", name="uq_idx_breadth"),)

    id: int                = Column(Integer, primary_key=True, autoincrement=True)
    index_code: str        = Column(String(10), nullable=False, index=True)
    date: date             = Column(Date, nullable=False, index=True)
    total_assets: int      = Column(Integer, nullable=False, default=0)
    pct_sma21: float       = Column(Float, nullable=False, default=0.0)
    pct_sma50: float       = Column(Float, nullable=False, default=0.0)
    pct_sma200: float      = Column(Float, nullable=False, default=0.0)
    pct_rsi_oversold: float  = Column(Float, nullable=True, default=0.0)
    pct_rsi_neutral: float   = Column(Float, nullable=True, default=0.0)
    pct_rsi_overbought: float = Column(Float, nullable=True, default=0.0)

    def __repr__(self) -> str:
        return f"<IndexBreadth {self.index_code} {self.date}>"
