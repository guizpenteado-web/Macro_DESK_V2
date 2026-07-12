from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class AssetPriceHistory(Base):
    """Cotacao diaria (OHLC) via brapi.dev — a CVM nao publica preco de
    pregao em nenhum dos datasets ja usados neste projeto (CDA so tem
    posicao mensal de fundos, sem candlestick). Fonte de mercado externa,
    fora do pipeline CVM. Chave por ticker (nao por Asset.id) porque nem
    todo ticker cobre pela VLMO/Insiders tem posicao de fundo — Asset so
    existe pra quem aparece no CDA. Cache local, revalidado se o ultimo
    ponto tiver mais de 1 dia (ver services/price_ingestion.py)."""

    __tablename__ = "asset_price_history"
    __table_args__ = (UniqueConstraint("ticker", "trade_date", name="uq_asset_price_ticker_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    open: Mapped[float] = mapped_column(Numeric(18, 4))
    high: Mapped[float] = mapped_column(Numeric(18, 4))
    low: Mapped[float] = mapped_column(Numeric(18, 4))
    close: Mapped[float] = mapped_column(Numeric(18, 4))
    volume: Mapped[float | None] = mapped_column(Numeric(20, 2))

    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
