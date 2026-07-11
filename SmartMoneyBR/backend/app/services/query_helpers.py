from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FundAssetMovement, FundHolding


def latest_holdings_ref_date(db: Session) -> date | None:
    return db.execute(select(func.max(FundHolding.ref_date))).scalar_one_or_none()


def latest_movements_ref_date(db: Session) -> date | None:
    return db.execute(select(func.max(FundAssetMovement.ref_date))).scalar_one_or_none()
