from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.database import get_db
from app.models import Asset, Fund, FundAssetMovement, FundHolding, FundNav, FundQuota
from app.schemas.fund import AssetHistoryPoint, FundOut, HoldingOut, MovementOut
from app.services import nav_lookup
from app.services.returns import compute_window_return

router = APIRouter(prefix="/api/funds", tags=["funds"])

RETURN_WINDOW_DAYS = 370  # ~12 meses + folga p/ cobrir fundos com divulgacao atrasada
SortField = Literal[
    "name", "net_asset_value", "n_shareholders", "financials_ref_date", "return_pct_12m", "return_pct_mtd", "return_pct_ytd"
]


def _latest_fund_holdings_date(db: Session, fund_id: int) -> date | None:
    """Per-FUND latest available month — not the system-wide latest. Many
    funds lag behind the freshest month (late filers, reporting gaps), so
    defaulting to a global date silently returns an empty result for them."""
    return db.execute(
        select(func.max(FundHolding.ref_date)).where(FundHolding.fund_id == fund_id)
    ).scalar_one_or_none()


def _latest_fund_movements_date(db: Session, fund_id: int) -> date | None:
    return db.execute(
        select(func.max(FundAssetMovement.ref_date)).where(FundAssetMovement.fund_id == fund_id)
    ).scalar_one_or_none()


def _latest_quota_by_fund(db: Session, fund_ids: list[int]) -> dict[int, FundQuota]:
    """Latest fund_quota row (patrimonio + n_cotistas + data) per fund, in one
    query — DISTINCT ON is Postgres' idiomatic 'latest row per group'."""
    if not fund_ids:
        return {}
    rows = db.execute(
        select(FundQuota)
        .where(FundQuota.fund_id.in_(fund_ids))
        .distinct(FundQuota.fund_id)
        .order_by(FundQuota.fund_id, FundQuota.ref_date.desc())
    ).scalars()
    return {q.fund_id: q for q in rows}


def _to_fund_out(
    fund: Fund,
    quota: FundQuota | None,
    return_pct_12m: float | None,
    return_pct_mtd: float | None = None,
    return_pct_ytd: float | None = None,
) -> FundOut:
    return FundOut(
        id=fund.id,
        cnpj=fund.cnpj,
        name=fund.name,
        fund_class_type=fund.fund_class_type,
        net_asset_value=float(quota.net_asset_value) if quota else None,
        n_shareholders=quota.n_shareholders if quota else None,
        financials_ref_date=quota.ref_date if quota else None,
        return_pct_12m=return_pct_12m,
        return_pct_mtd=return_pct_mtd,
        return_pct_ytd=return_pct_ytd,
    )


def _return_pct_12m_by_fund(db: Session, fund_ids: list[int], quotas: dict[int, FundQuota]) -> dict[int, float]:
    """~12-month real return (quota value, rebase-corrected) per fund, anchored
    to each fund's OWN latest quota date (funds lag differently) rather than a
    single global date. Fetched in one bounded query, not N+1."""
    if not fund_ids:
        return {}
    last_dates = [quotas[fid].ref_date for fid in fund_ids if fid in quotas]
    if not last_dates:
        return {}
    earliest_needed = min(last_dates) - timedelta(days=RETURN_WINDOW_DAYS)

    rows = db.execute(
        select(FundQuota.fund_id, FundQuota.ref_date, FundQuota.quota_value)
        .where(FundQuota.fund_id.in_(fund_ids), FundQuota.ref_date >= earliest_needed)
        .order_by(FundQuota.fund_id, FundQuota.ref_date)
    ).all()

    series_by_fund: dict[int, list[tuple[date, float]]] = {}
    for r in rows:
        series_by_fund.setdefault(r.fund_id, []).append((r.ref_date, float(r.quota_value)))

    results = {}
    for fund_id, series in series_by_fund.items():
        if fund_id not in quotas:
            continue
        window_start = quotas[fund_id].ref_date - timedelta(days=RETURN_WINDOW_DAYS)
        pct_return, _ = compute_window_return(series, window_start)
        if pct_return is not None:
            results[fund_id] = pct_return
    return results


def _return_window_by_fund(
    db: Session, fund_ids: list[int], quotas: dict[int, FundQuota], window_start_fn
) -> dict[int, float]:
    """Generic helper for MTD/YTD — same rebase-safe logic as
    _return_pct_12m_by_fund, just with a caller-supplied window_start per
    fund instead of a fixed ~365-day lookback. window_start_fn(latest_ref_date)
    -> date."""
    if not fund_ids:
        return {}
    starts = {fid: window_start_fn(quotas[fid].ref_date) for fid in fund_ids if fid in quotas}
    if not starts:
        return {}
    earliest_needed = min(starts.values())

    rows = db.execute(
        select(FundQuota.fund_id, FundQuota.ref_date, FundQuota.quota_value)
        .where(FundQuota.fund_id.in_(fund_ids), FundQuota.ref_date >= earliest_needed)
        .order_by(FundQuota.fund_id, FundQuota.ref_date)
    ).all()

    series_by_fund: dict[int, list[tuple[date, float]]] = {}
    for r in rows:
        series_by_fund.setdefault(r.fund_id, []).append((r.ref_date, float(r.quota_value)))

    results = {}
    for fund_id, series in series_by_fund.items():
        if fund_id not in starts:
            continue
        pct_return, _ = compute_window_return(series, starts[fund_id])
        if pct_return is not None:
            results[fund_id] = pct_return
    return results


def _return_mtd_by_fund(db: Session, fund_ids: list[int], quotas: dict[int, FundQuota]) -> dict[int, float]:
    """Retorno do mes corrente: ultima cota vs cota do fechamento do mes
    anterior. FundQuota so tem granularidade mensal (uma linha por mes),
    entao "mes corrente" na pratica e' sempre "ultimo mes fechado vs
    penultimo" — window_start alguns dias antes do inicio do mes da
    ultima cota garante que o fechamento anterior entre na janela."""
    def window_start(last_ref_date: date) -> date:
        first_of_month = last_ref_date.replace(day=1)
        return first_of_month - timedelta(days=5)

    return _return_window_by_fund(db, fund_ids, quotas, window_start)


def _return_ytd_by_fund(db: Session, fund_ids: list[int], quotas: dict[int, FundQuota]) -> dict[int, float]:
    """Retorno acumulado no ano: ultima cota vs fechamento de dezembro do
    ano anterior (base do YTD)."""
    def window_start(last_ref_date: date) -> date:
        return date(last_ref_date.year - 1, 12, 1)

    return _return_window_by_fund(db, fund_ids, quotas, window_start)


@router.get("", response_model=list[FundOut])
def search_funds(
    search: str = Query("", min_length=0),
    limit: int = 25,
    min_net_asset_value: float | None = None,
    max_net_asset_value: float | None = None,
    min_shareholders: int | None = None,
    max_shareholders: int | None = None,
    ref_date_from: date | None = None,
    ref_date_to: date | None = None,
    min_return_pct: float | None = None,
    max_return_pct: float | None = None,
    sort_by: SortField = "name",
    sort_dir: Literal["asc", "desc"] = "asc",
    db: Session = Depends(get_db),
):
    # Phase 1 only tracks the equities CDA block — most CVM-registered funds
    # are fixed-income/multimercado/credit vehicles that never hold a single
    # stock, so listing them here just leads to a fund page with permanently
    # empty tables. Restrict search to funds that have at least one recorded
    # equity holding (ever), which is the only subset this app has data for.
    has_equity = select(FundHolding.fund_id).distinct().subquery()

    # Latest fund_quota row per fund (patrimonio/cotistas/data de divulgacao) —
    # joined in SQL so nav/cotistas/data filters can run as indexed WHERE
    # clauses instead of loading everything into Python first.
    # Achado 16/jul/2026: sem o WHERE fund_id IN (has_equity) aqui, o DISTINCT
    # ON roda sobre os ~55 mil fundos de fund_quota inteiro (a maioria sem
    # nenhuma posicao de equity, fora do escopo do app) em vez dos ~9,3 mil
    # que realmente importam — EXPLAIN ANALYZE mediu ~4s a mais nesse passo
    # sozinho. Filtrar antes do DISTINCT ON reduz a base de sort/dedup em ~6x.
    latest_quota_sq = (
        select(FundQuota)
        .where(FundQuota.fund_id.in_(select(has_equity.c.fund_id)))
        .distinct(FundQuota.fund_id)
        .order_by(FundQuota.fund_id, FundQuota.ref_date.desc())
        .subquery()
    )
    LatestQuota = aliased(FundQuota, latest_quota_sq)

    stmt = (
        select(Fund, LatestQuota)
        .join(LatestQuota, LatestQuota.fund_id == Fund.id)
        .where(Fund.id.in_(select(has_equity.c.fund_id)))
    )
    if search:
        stmt = stmt.where(Fund.name.ilike(f"%{search}%") | Fund.cnpj.ilike(f"%{search}%"))
    if min_net_asset_value is not None:
        stmt = stmt.where(LatestQuota.net_asset_value >= min_net_asset_value)
    if max_net_asset_value is not None:
        stmt = stmt.where(LatestQuota.net_asset_value <= max_net_asset_value)
    if min_shareholders is not None:
        stmt = stmt.where(LatestQuota.n_shareholders >= min_shareholders)
    if max_shareholders is not None:
        stmt = stmt.where(LatestQuota.n_shareholders <= max_shareholders)
    if ref_date_from is not None:
        stmt = stmt.where(LatestQuota.ref_date >= ref_date_from)
    if ref_date_to is not None:
        stmt = stmt.where(LatestQuota.ref_date <= ref_date_to)

    # Achado 16/jul/2026 — pagina /fundos "nao carregava" em producao:
    # sort+limit rodava so no final, em Python, DEPOIS de calcular
    # 12m/MTD/YTD (3 queries + rebase em Python) pra TODO fundo com
    # equity (milhares) que batesse nos filtros de NAV/cotistas/data —
    # sem filtro nenhum isso levava >15s (medido no VPS). Os campos de
    # retorno sao calculados, nao existem como coluna pra ordenar em SQL,
    # entao só da pra empurrar sort+limit pro banco quando o sort_by e um
    # campo nativo (nome/NAV/cotistas/data) E nao ha filtro de retorno
    # (que exige ter o valor calculado de todo mundo pra filtrar certo).
    # Caso comum (sort padrao "name", sem filtro de retorno) cai nesse
    # atalho e so calcula retorno pros ~25-50 fundos da pagina, nao pra
    # milhares.
    needs_full_scan = (
        sort_by in ("return_pct_12m", "return_pct_mtd", "return_pct_ytd")
        or min_return_pct is not None
        or max_return_pct is not None
    )

    if not needs_full_scan:
        sql_order_col = {
            "name": Fund.name,
            "net_asset_value": LatestQuota.net_asset_value,
            "n_shareholders": LatestQuota.n_shareholders,
            "financials_ref_date": LatestQuota.ref_date,
        }[sort_by]
        order_expr = sql_order_col.desc().nulls_last() if sort_dir == "desc" else sql_order_col.asc().nulls_last()
        stmt = stmt.order_by(order_expr).limit(limit)

    rows = db.execute(stmt).all()
    funds = [row[0] for row in rows]
    quotas = {row[0].id: row[1] for row in rows}

    fund_ids = [f.id for f in funds]
    return_by_fund = _return_pct_12m_by_fund(db, fund_ids, quotas)
    mtd_by_fund = _return_mtd_by_fund(db, fund_ids, quotas)
    ytd_by_fund = _return_ytd_by_fund(db, fund_ids, quotas)

    out = [
        _to_fund_out(f, quotas.get(f.id), return_by_fund.get(f.id), mtd_by_fund.get(f.id), ytd_by_fund.get(f.id))
        for f in funds
    ]

    if not needs_full_scan:
        # Ja veio ordenado e limitado do SQL — so' preserva a ordem.
        return out

    if min_return_pct is not None:
        out = [o for o in out if o.return_pct_12m is not None and o.return_pct_12m >= min_return_pct]
    if max_return_pct is not None:
        out = [o for o in out if o.return_pct_12m is not None and o.return_pct_12m <= max_return_pct]

    sort_key = {
        "name": lambda o: o.name,
        "net_asset_value": lambda o: (o.net_asset_value is None, o.net_asset_value or 0),
        "n_shareholders": lambda o: (o.n_shareholders is None, o.n_shareholders or 0),
        "financials_ref_date": lambda o: (o.financials_ref_date is None, o.financials_ref_date or date.min),
        "return_pct_12m": lambda o: (o.return_pct_12m is None, o.return_pct_12m or 0),
        "return_pct_mtd": lambda o: (o.return_pct_mtd is None, o.return_pct_mtd or 0),
        "return_pct_ytd": lambda o: (o.return_pct_ytd is None, o.return_pct_ytd or 0),
    }[sort_by]
    out.sort(key=sort_key, reverse=(sort_dir == "desc"))

    return out[:limit]


@router.get("/{fund_id}", response_model=FundOut)
def get_fund(fund_id: int, db: Session = Depends(get_db)):
    fund = db.get(Fund, fund_id)
    if not fund:
        raise HTTPException(404, "Fundo nao encontrado")
    quotas = _latest_quota_by_fund(db, [fund_id])
    return_pct = _return_pct_12m_by_fund(db, [fund_id], quotas).get(fund_id)
    mtd = _return_mtd_by_fund(db, [fund_id], quotas).get(fund_id)
    ytd = _return_ytd_by_fund(db, [fund_id], quotas).get(fund_id)
    return _to_fund_out(fund, quotas.get(fund_id), return_pct, mtd, ytd)


@router.get("/{fund_id}/holdings", response_model=list[HoldingOut])
def get_fund_holdings(fund_id: int, ref_date: date | None = None, db: Session = Depends(get_db)):
    target_date = ref_date or _latest_fund_holdings_date(db, fund_id)
    if target_date is None:
        return []

    rows = db.execute(
        select(FundHolding.asset_id, Asset.ticker, Asset.company_name, FundHolding.quantity, FundHolding.market_value)
        .join(Asset, Asset.id == FundHolding.asset_id)
        .where(FundHolding.fund_id == fund_id, FundHolding.ref_date == target_date)
        .order_by(FundHolding.market_value.desc())
    ).all()

    nav = db.execute(
        select(FundNav.net_asset_value).where(FundNav.fund_id == fund_id, FundNav.ref_date == target_date)
    ).scalar_one_or_none()
    total_equities = sum(float(r.market_value) for r in rows) or None

    return [
        HoldingOut(
            asset_id=r.asset_id,
            ticker=r.ticker,
            company_name=r.company_name,
            quantity=float(r.quantity),
            market_value=float(r.market_value),
            pct_of_equity_book=(float(r.market_value) / total_equities * 100) if total_equities else None,
            ref_date=target_date,
        )
        for r in rows
    ]


@router.get("/{fund_id}/movements", response_model=list[MovementOut])
def get_fund_movements(fund_id: int, ref_date: date | None = None, db: Session = Depends(get_db)):
    target_date = ref_date or _latest_fund_movements_date(db, fund_id)
    if target_date is None:
        return []

    rows = db.execute(
        select(FundAssetMovement, Asset.ticker)
        .join(Asset, Asset.id == FundAssetMovement.asset_id)
        .where(FundAssetMovement.fund_id == fund_id, FundAssetMovement.ref_date == target_date)
        .order_by(FundAssetMovement.value_delta.desc())
    ).all()

    return [
        MovementOut(
            asset_id=m.asset_id,
            ticker=ticker,
            classification=m.classification.value,
            ref_date=m.ref_date,
            prior_ref_date=m.prior_ref_date,
            qty_current=float(m.qty_current),
            qty_prior=float(m.qty_prior),
            value_current=float(m.value_current),
            value_prior=float(m.value_prior),
            qty_delta=float(m.qty_delta),
            value_delta=float(m.value_delta),
            pct_delta=float(m.pct_delta) if m.pct_delta is not None else None,
        )
        for m, ticker in rows
    ]


@router.get("/{fund_id}/history", response_model=list[AssetHistoryPoint])
def get_fund_asset_history(fund_id: int, asset_id: int, db: Session = Depends(get_db)):
    """Full accumulated-position timeline for one fund+asset pair, each point
    explicitly labeled with its movement classification — the original ask:
    'evolucao acumulada explicitamente rotulada aumento/reducao'. Also
    carries pct_of_fund (mesma logica staleness-guarded de
    assets.py::get_asset_holders via app.services.nav_lookup) — usado no
    grafico tipo carteirafundos.com (candlestick + paineis empilhados)."""
    holdings = db.execute(
        select(FundHolding.ref_date, FundHolding.quantity, FundHolding.market_value)
        .where(FundHolding.fund_id == fund_id, FundHolding.asset_id == asset_id)
        .order_by(FundHolding.ref_date)
    ).all()
    if not holdings:
        return []

    movements = {
        m.ref_date: m
        for m in db.execute(
            select(FundAssetMovement)
            .where(FundAssetMovement.fund_id == fund_id, FundAssetMovement.asset_id == asset_id)
        ).scalars()
    }

    nav_rows = db.execute(
        select(FundNav.ref_date, FundNav.net_asset_value).where(FundNav.fund_id == fund_id).order_by(FundNav.ref_date)
    ).all()
    nav_by_date = {r.ref_date: float(r.net_asset_value) for r in nav_rows}
    navs_sorted = [(r.ref_date, float(r.net_asset_value)) for r in nav_rows]

    quota_rows = db.execute(
        select(FundQuota.ref_date, FundQuota.net_asset_value).where(FundQuota.fund_id == fund_id).order_by(FundQuota.ref_date)
    ).all()
    quotas_sorted = [(r.ref_date, float(r.net_asset_value)) for r in quota_rows]

    portfolio_rows = db.execute(
        select(FundHolding.ref_date, func.sum(FundHolding.market_value))
        .where(FundHolding.fund_id == fund_id)
        .group_by(FundHolding.ref_date)
    ).all()
    portfolio_totals = {r[0]: float(r[1]) for r in portfolio_rows}

    results = []
    for h in holdings:
        mv = float(h.market_value)
        portfolio_total = portfolio_totals.get(h.ref_date, 0.0)
        nav = nav_lookup.nav_as_of(h.ref_date, portfolio_total, nav_by_date.get(h.ref_date), navs_sorted)
        if nav is None:
            nav = nav_lookup.quota_fallback(h.ref_date, mv, portfolio_total, quotas_sorted)
        results.append(
            AssetHistoryPoint(
                ref_date=h.ref_date,
                quantity=float(h.quantity),
                market_value=mv,
                classification=movements[h.ref_date].classification.value if h.ref_date in movements else None,
                qty_delta=float(movements[h.ref_date].qty_delta) if h.ref_date in movements else None,
                pct_of_fund=(mv / nav * 100) if nav else None,
            )
        )
    return results
