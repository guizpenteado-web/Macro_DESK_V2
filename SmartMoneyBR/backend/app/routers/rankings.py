from datetime import date
from enum import Enum

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, FundAssetMovement, MovementClassification
from app.services.query_helpers import latest_movements_ref_date

router = APIRouter(prefix="/api/rankings", tags=["rankings"])


class RankingKind(str, Enum):
    most_bought = "most-bought"
    most_sold = "most-sold"
    most_increased = "most-increased"
    most_decreased = "most-decreased"
    most_new = "most-new"
    most_closed = "most-closed"


_KIND_TO_CLASS = {
    RankingKind.most_increased: MovementClassification.INCREASED,
    RankingKind.most_decreased: MovementClassification.DECREASED,
    RankingKind.most_new: MovementClassification.NEW,
    RankingKind.most_closed: MovementClassification.CLOSED,
}


@router.get("/{kind}")
def get_ranking(kind: RankingKind, ref_date: date | None = None, limit: int = 20, db: Session = Depends(get_db)):
    target_date = ref_date or latest_movements_ref_date(db)
    if target_date is None:
        return {"ref_date": None, "rows": []}

    if kind in (RankingKind.most_bought, RankingKind.most_sold):
        # Gross buying/selling pressure: sum of value_delta restricted to the
        # relevant classifications, NOT netted against the opposite direction.
        classes = (
            [MovementClassification.NEW, MovementClassification.INCREASED]
            if kind == RankingKind.most_bought
            else [MovementClassification.DECREASED, MovementClassification.CLOSED]
        )
        stmt = (
            select(
                Asset.id.label("asset_id"),
                Asset.ticker,
                Asset.company_name,
                func.count(func.distinct(FundAssetMovement.fund_id)).label("n_funds"),
                func.sum(FundAssetMovement.qty_delta).label("net_qty_delta"),
                func.sum(FundAssetMovement.value_delta).label("net_value_delta"),
            )
            .join(FundAssetMovement, FundAssetMovement.asset_id == Asset.id)
            .where(
                FundAssetMovement.ref_date == target_date,
                FundAssetMovement.classification.in_(classes),
                Asset.is_active.is_(True),
            )
            .group_by(Asset.id, Asset.ticker, Asset.company_name)
        )
        order_col = "net_value_delta"
        desc = kind == RankingKind.most_bought
    else:
        classification = _KIND_TO_CLASS[kind]
        stmt = (
            select(
                Asset.id.label("asset_id"),
                Asset.ticker,
                Asset.company_name,
                func.count(func.distinct(FundAssetMovement.fund_id)).label("n_funds"),
                func.sum(FundAssetMovement.qty_delta).label("net_qty_delta"),
                func.sum(FundAssetMovement.value_delta).label("net_value_delta"),
            )
            .join(FundAssetMovement, FundAssetMovement.asset_id == Asset.id)
            .where(
                FundAssetMovement.ref_date == target_date,
                FundAssetMovement.classification == classification,
                Asset.is_active.is_(True),
            )
            .group_by(Asset.id, Asset.ticker, Asset.company_name)
        )
        order_col = "n_funds"
        desc = True

    order_expr = stmt.selected_columns[order_col]
    stmt = stmt.order_by(order_expr.desc() if desc else order_expr.asc()).limit(limit)

    rows = db.execute(stmt).all()
    return {
        "ref_date": target_date,
        "kind": kind.value,
        "rows": [
            {
                "asset_id": r.asset_id,
                "ticker": r.ticker,
                "company_name": r.company_name,
                "n_funds": r.n_funds,
                "net_qty_delta": float(r.net_qty_delta),
                "net_value_delta": float(r.net_value_delta),
            }
            for r in rows
        ],
    }


@router.get("/consensus/top")
def get_consensus_ranking(ref_date: date | None = None, limit: int = 20, db: Session = Depends(get_db)):
    """'Institutional consensus' — assets held by the most funds this month
    (independent of movement direction), e.g. PETR4 held by 94 funds."""
    from app.models import FundHolding

    target_date = ref_date
    if target_date is None:
        target_date = db.execute(select(func.max(FundHolding.ref_date))).scalar_one_or_none()
    if target_date is None:
        return {"ref_date": None, "rows": []}

    rows = db.execute(
        select(
            Asset.id.label("asset_id"),
            Asset.ticker,
            Asset.company_name,
            func.count(func.distinct(FundHolding.fund_id)).label("n_funds"),
            func.sum(FundHolding.market_value).label("total_value"),
        )
        .join(FundHolding, FundHolding.asset_id == Asset.id)
        .where(FundHolding.ref_date == target_date, Asset.is_active.is_(True))
        .group_by(Asset.id, Asset.ticker, Asset.company_name)
        .order_by(func.count(func.distinct(FundHolding.fund_id)).desc())
        .limit(limit)
    ).all()

    return {
        "ref_date": target_date,
        "rows": [
            {
                "asset_id": r.asset_id,
                "ticker": r.ticker,
                "company_name": r.company_name,
                "n_funds": r.n_funds,
                "total_value": float(r.total_value),
            }
            for r in rows
        ],
    }
