from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FundHolding(Base):
    """One row per fund+asset+reference-month. Never overwritten across months —
    a different ref_date always gets its own row. Re-ingesting the SAME month
    (CDA refreshes the last 3 months daily) is an upsert keyed on the unique
    constraint below, not a loss of history."""

    __tablename__ = "fund_holdings"
    __table_args__ = (
        UniqueConstraint("fund_id", "asset_id", "ref_date", name="uq_fund_holdings_fund_asset_month"),
        Index("ix_fund_holdings_asset_refdate", "asset_id", "ref_date"),
        Index("ix_fund_holdings_refdate", "ref_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    ref_date: Mapped[date] = mapped_column(Date)

    quantity: Mapped[float] = mapped_column(Numeric(20, 6))
    market_value: Mapped[float] = mapped_column(Numeric(20, 2))

    source_file: Mapped[str | None] = mapped_column(String(120))
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FundNav(Base):
    """VL_PATRIM_LIQ from the CDA PL file — comes free in the same monthly zip,
    ingested alongside holdings so '% of portfolio' can be computed against real
    fund net asset value from day one instead of waiting for Informe Diario."""

    __tablename__ = "fund_nav"
    __table_args__ = (
        UniqueConstraint("fund_id", "ref_date", name="uq_fund_nav_fund_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    ref_date: Mapped[date] = mapped_column(Date)
    net_asset_value: Mapped[float] = mapped_column(Numeric(20, 2))
