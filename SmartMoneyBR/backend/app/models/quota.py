from datetime import date

from sqlalchemy import Date, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FundQuota(Base):
    """Monthly snapshot (last trading day of the month) from CVM's Informe
    Diario — quota value lets us compute REAL investment return, unlike
    fund_nav (patrimonio liquido from CDA/PL) which conflates return with
    subscriptions/redemptions. Sourced separately because Informe Diario's
    historical depth (2000-present) is much longer than CDA's (2024-07+)."""

    __tablename__ = "fund_quota"
    __table_args__ = (
        UniqueConstraint("fund_id", "ref_date", name="uq_fund_quota_fund_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"), index=True)
    ref_date: Mapped[date] = mapped_column(Date, index=True)

    quota_value: Mapped[float] = mapped_column(Numeric(24, 12))
    net_asset_value: Mapped[float] = mapped_column(Numeric(20, 2))
    n_shareholders: Mapped[int | None] = mapped_column()
