import enum
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class MovementClassification(str, enum.Enum):
    NEW = "NEW"
    INCREASED = "INCREASED"
    DECREASED = "DECREASED"
    CLOSED = "CLOSED"
    UNCHANGED = "UNCHANGED"


class FundAssetMovement(Base):
    """Derived table produced by the comparison engine — one row per
    fund+asset+month classifying the month-over-month change."""

    __tablename__ = "fund_asset_movements"
    __table_args__ = (
        UniqueConstraint("fund_id", "asset_id", "ref_date", name="uq_movements_fund_asset_month"),
        Index("ix_movements_asset_refdate", "asset_id", "ref_date"),
        Index("ix_movements_fund_refdate", "fund_id", "ref_date"),
        Index("ix_movements_classification_refdate", "classification", "ref_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), index=True)
    ref_date: Mapped[date] = mapped_column(Date)
    prior_ref_date: Mapped[date | None] = mapped_column(Date)

    classification: Mapped[MovementClassification] = mapped_column(Enum(MovementClassification, name="movement_classification"))

    qty_current: Mapped[float] = mapped_column(Numeric(20, 6))
    qty_prior: Mapped[float] = mapped_column(Numeric(20, 6))
    value_current: Mapped[float] = mapped_column(Numeric(20, 2))
    value_prior: Mapped[float] = mapped_column(Numeric(20, 2))
    qty_delta: Mapped[float] = mapped_column(Numeric(20, 6))
    value_delta: Mapped[float] = mapped_column(Numeric(20, 2))
    # Clamped in the comparison engine (see comparison_engine.py) before insert —
    # a position moving from a near-zero residual to a full position produces a
    # meaningless multi-million-percent change; widened here too as a safety margin.
    pct_delta: Mapped[float | None] = mapped_column(Numeric(14, 4))

    computed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
