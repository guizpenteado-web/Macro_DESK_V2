from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Fund, FundAssetMovement, FundHolding, FundQuota
from app.schemas.asset import AssetHolderOut, AssetOut, AssetTimelinePoint
from app.services.query_helpers import latest_holdings_ref_date, latest_movements_ref_date

router = APIRouter(prefix="/api/assets", tags=["assets"])

RETURN_WINDOW_DAYS = 370  # ~12 meses + folga p/ ativos com divulgacao atrasada
AssetSortField = Literal["ticker", "total_market_value", "return_pct_12m"]


def _latest_holdings_agg_by_asset(db: Session, asset_ids: list[int] | None = None) -> dict[int, tuple[date, float, float]]:
    """Ultimo mes de divulgacao POR ATIVO (nao um mes global — ativos podem ter
    divulgacoes defasadas entre si) com quantidade e valor somados entre todos
    os fundos que detem aquele ativo naquele mes."""
    latest_date_q = select(FundHolding.asset_id, func.max(FundHolding.ref_date).label("ref_date")).group_by(
        FundHolding.asset_id
    )
    if asset_ids is not None:
        latest_date_q = latest_date_q.where(FundHolding.asset_id.in_(asset_ids))
    latest_date_sq = latest_date_q.subquery()

    rows = db.execute(
        select(
            FundHolding.asset_id,
            FundHolding.ref_date,
            func.sum(FundHolding.quantity).label("total_quantity"),
            func.sum(FundHolding.market_value).label("total_value"),
        )
        .join(
            latest_date_sq,
            (latest_date_sq.c.asset_id == FundHolding.asset_id) & (latest_date_sq.c.ref_date == FundHolding.ref_date),
        )
        .group_by(FundHolding.asset_id, FundHolding.ref_date)
    ).all()
    return {r.asset_id: (r.ref_date, float(r.total_quantity), float(r.total_value)) for r in rows}


def _return_pct_12m_by_asset(db: Session, asset_ids: list[int], latest: dict[int, tuple[date, float, float]]) -> dict[int, float]:
    """~12-month price return per asset, using the aggregate market_value/quantity
    ratio (implied price) across all funds that hold it — real market price, so
    unlike fund quotas there's no flow-vs-return ambiguity to correct for."""
    if not asset_ids:
        return {}
    last_dates = [latest[aid][0] for aid in asset_ids if aid in latest]
    if not last_dates:
        return {}
    earliest_needed = min(last_dates) - timedelta(days=RETURN_WINDOW_DAYS)

    rows = db.execute(
        select(
            FundHolding.asset_id,
            FundHolding.ref_date,
            func.sum(FundHolding.quantity).label("total_quantity"),
            func.sum(FundHolding.market_value).label("total_value"),
        )
        .where(FundHolding.asset_id.in_(asset_ids), FundHolding.ref_date >= earliest_needed)
        .group_by(FundHolding.asset_id, FundHolding.ref_date)
        .order_by(FundHolding.asset_id, FundHolding.ref_date)
    ).all()

    series_by_asset: dict[int, list[tuple[date, float]]] = {}
    for r in rows:
        if r.total_quantity:
            series_by_asset.setdefault(r.asset_id, []).append((r.ref_date, float(r.total_value) / float(r.total_quantity)))

    results = {}
    for asset_id, series in series_by_asset.items():
        if asset_id not in latest:
            continue
        window_start = latest[asset_id][0] - timedelta(days=RETURN_WINDOW_DAYS)
        in_window = [(d, p) for d, p in series if d >= window_start]
        if len(in_window) < 2:
            continue
        first_price = in_window[0][1]
        last_price = in_window[-1][1]
        if first_price > 0:
            results[asset_id] = (last_price / first_price - 1) * 100
    return results


def _to_asset_out(asset: Asset, latest: dict[int, tuple[date, float, float]], return_by_asset: dict[int, float]) -> AssetOut:
    info = latest.get(asset.id)
    return AssetOut(
        id=asset.id,
        ticker=asset.ticker,
        company_name=asset.company_name,
        asset_type=asset.asset_type,
        total_market_value=info[2] if info else None,
        financials_ref_date=info[0] if info else None,
        return_pct_12m=return_by_asset.get(asset.id),
    )


@router.get("", response_model=list[AssetOut])
def search_assets(
    search: str = Query("", min_length=0),
    asset_type: Literal["equity", "bdr", ""] = "",
    limit: int = 25,
    min_total_market_value: float | None = None,
    min_return_pct: float | None = None,
    max_return_pct: float | None = None,
    sort_by: AssetSortField = "ticker",
    sort_dir: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
):
    stmt = select(Asset)
    if search:
        stmt = stmt.where(Asset.ticker.ilike(f"%{search}%") | Asset.company_name.ilike(f"%{search}%"))
    if asset_type:
        stmt = stmt.where(Asset.asset_type == asset_type)
    assets = db.execute(stmt).scalars().all()

    asset_ids = [a.id for a in assets]
    latest = _latest_holdings_agg_by_asset(db, asset_ids)
    return_by_asset = _return_pct_12m_by_asset(db, asset_ids, latest)

    out = [_to_asset_out(a, latest, return_by_asset) for a in assets]

    if min_total_market_value is not None:
        out = [o for o in out if o.total_market_value is not None and o.total_market_value >= min_total_market_value]
    if min_return_pct is not None:
        out = [o for o in out if o.return_pct_12m is not None and o.return_pct_12m >= min_return_pct]
    if max_return_pct is not None:
        out = [o for o in out if o.return_pct_12m is not None and o.return_pct_12m <= max_return_pct]

    sort_key = {
        "ticker": lambda o: o.ticker,
        "total_market_value": lambda o: (o.total_market_value is None, o.total_market_value or 0),
        "return_pct_12m": lambda o: (o.return_pct_12m is None, o.return_pct_12m or 0),
    }[sort_by]
    out.sort(key=sort_key, reverse=(sort_dir == "desc"))

    return out[:limit]


@router.get("/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, db: Session = Depends(get_db)):
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(404, "Ativo nao encontrado")
    latest = _latest_holdings_agg_by_asset(db, [asset_id])
    return_by_asset = _return_pct_12m_by_asset(db, [asset_id], latest)
    return _to_asset_out(asset, latest, return_by_asset)


@router.get("/{asset_id}/holders", response_model=list[AssetHolderOut])
def get_asset_holders(asset_id: int, ref_date: date | None = None, db: Session = Depends(get_db)):
    """Who holds this asset this month, ranked by position size, with the
    movement classification/delta joined in so buyers/sellers are visible
    at a glance."""
    target_date = ref_date or latest_holdings_ref_date(db)
    if target_date is None:
        return []

    rows = db.execute(
        select(FundHolding, Fund.name, Fund.cnpj, FundAssetMovement.classification, FundAssetMovement.qty_delta)
        .join(Fund, Fund.id == FundHolding.fund_id)
        .outerjoin(
            FundAssetMovement,
            (FundAssetMovement.fund_id == FundHolding.fund_id)
            & (FundAssetMovement.asset_id == FundHolding.asset_id)
            & (FundAssetMovement.ref_date == FundHolding.ref_date),
        )
        .where(FundHolding.asset_id == asset_id, FundHolding.ref_date == target_date)
        .order_by(FundHolding.market_value.desc())
    ).all()

    # Patrimonio/cotistas do fundo como um todo (nao so a posicao neste ativo) —
    # pega o fund_quota mais recente de cada fundo, em uma unica query.
    fund_ids = [h.fund_id for h, *_ in rows]
    quotas = {}
    if fund_ids:
        quota_rows = db.execute(
            select(FundQuota)
            .where(FundQuota.fund_id.in_(fund_ids))
            .distinct(FundQuota.fund_id)
            .order_by(FundQuota.fund_id, FundQuota.ref_date.desc())
        ).scalars()
        quotas = {q.fund_id: q for q in quota_rows}

    return [
        AssetHolderOut(
            fund_id=h.fund_id,
            fund_name=name,
            fund_cnpj=cnpj,
            quantity=float(h.quantity),
            market_value=float(h.market_value),
            classification=classification.value if classification else None,
            qty_delta=float(qty_delta) if qty_delta is not None else None,
            ref_date=h.ref_date,
            fund_net_asset_value=float(quotas[h.fund_id].net_asset_value) if h.fund_id in quotas else None,
            fund_n_shareholders=quotas[h.fund_id].n_shareholders if h.fund_id in quotas else None,
        )
        for h, name, cnpj, classification, qty_delta in rows
    ]


@router.get("/{asset_id}/movements")
def get_asset_movements(asset_id: int, ref_date: date | None = None, db: Session = Depends(get_db)):
    """Buyers/sellers ranking for this asset this month + net flow summary."""
    target_date = ref_date or latest_movements_ref_date(db)
    if target_date is None:
        return {"ref_date": None, "net_qty_delta": 0, "net_value_delta": 0, "movements": []}

    rows = db.execute(
        select(FundAssetMovement, Fund.name, Fund.cnpj)
        .join(Fund, Fund.id == FundAssetMovement.fund_id)
        .where(FundAssetMovement.asset_id == asset_id, FundAssetMovement.ref_date == target_date)
        .order_by(FundAssetMovement.value_delta.desc())
    ).all()

    net_qty_delta = sum(float(m.qty_delta) for m, _, _ in rows)
    net_value_delta = sum(float(m.value_delta) for m, _, _ in rows)

    return {
        "ref_date": target_date,
        "net_qty_delta": net_qty_delta,
        "net_value_delta": net_value_delta,
        "n_funds_buying": sum(1 for m, _, _ in rows if m.classification.value in ("NEW", "INCREASED")),
        "n_funds_selling": sum(1 for m, _, _ in rows if m.classification.value in ("DECREASED", "CLOSED")),
        "movements": [
            {
                "fund_id": m.fund_id,
                "fund_name": name,
                "fund_cnpj": cnpj,
                "classification": m.classification.value,
                "qty_delta": float(m.qty_delta),
                "value_delta": float(m.value_delta),
                "qty_current": float(m.qty_current),
            }
            for m, name, cnpj in rows
        ],
    }


@router.get("/{asset_id}/timeline", response_model=list[AssetTimelinePoint])
def get_asset_timeline(asset_id: int, db: Session = Depends(get_db)):
    rows = db.execute(
        select(
            FundHolding.ref_date,
            func.count(func.distinct(FundHolding.fund_id)).label("n_holders"),
            func.sum(FundHolding.quantity).label("total_quantity"),
            func.sum(FundHolding.market_value).label("total_value"),
        )
        .where(FundHolding.asset_id == asset_id)
        .group_by(FundHolding.ref_date)
        .order_by(FundHolding.ref_date)
    ).all()

    return [
        AssetTimelinePoint(
            ref_date=r.ref_date,
            n_holders=r.n_holders,
            total_quantity=float(r.total_quantity),
            total_value=float(r.total_value),
        )
        for r in rows
    ]
