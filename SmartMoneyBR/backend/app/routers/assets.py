from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, AssetPriceHistory, Fund, FundAssetMovement, FundHolding, FundNav, FundQuota, MovementClassification
from app.schemas.asset import AssetHolderOut, AssetOut, AssetTimelinePoint
from app.services import nav_lookup
from app.services.query_helpers import latest_movements_ref_date

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
    stmt = select(Asset).where(Asset.is_active.is_(True))
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


# Erro de preenchimento pontual confirmado na propria fonte CVM (nao no
# nosso pipeline): VC ENERGIA II FIP reporta VL_PATRIM_LIQ=R$1,76mi em
# 2025-06-30, contra R$29,5mi no mes anterior e R$295mi no mes seguinte —
# padrao em V que nenhuma estrutura de fundo real produziria de um mes pro
# outro. Excluido explicitamente (nao e' uma heuristica geral, so essa
# competencia especifica) — sem fallback via FundQuota (FIP nao tem Informe
# Diario), a posicao fica sem %PL exibido nesse mes em vez de mostrar um
# numero absurdo.
KNOWN_BAD_NAV_POINTS: set[tuple[int, date]] = {(823199, date(2025, 6, 30))}

STALE_HOLDER_LOOKBACK_DAYS = 365  # ~12 meses — 180d excluia fundos reais com atraso de entrega (achado 12/jul/2026: BB TOP
# ACOES SETOR IMOBILIARIO some da lista de MULT3 por estar 194 dias atrasado, apesar de ter posicao real e ativa).
# Distribuicao real (12/jul/2026): de ~9.3k fundos com alguma posicao historica, so 815 caem na faixa 366-730d e 4.484
# estao a mais de 730d (quase certamente fundos encerrados/liquidados sem baixa formal na CDA) — 365d cobre o atraso
# normal de entrega sem ressuscitar fundo genuinamente morto. O badge de "mes" na UI ja sinaliza posicao desatualizada.


@router.get("/{asset_id}/holders", response_model=list[AssetHolderOut])
def get_asset_holders(
    asset_id: int,
    ref_date: date | None = None,
    include_closed: bool = False,
    db: Session = Depends(get_db),
):
    """Who holds this asset, ranked by position size, with the movement
    classification/delta joined in so buyers/sellers are visible at a glance.

    Sem ref_date explicito, usa a ULTIMA posicao QUE CADA FUNDO JA DECLAROU
    nesse ativo (nao exige que todos batam na mesma data global). A CVM
    revisa/atrasa entrega de CDA por semanas conforme administradoras
    entregam declaracoes atrasadas (ver job_cda_recent) — exigir data exata
    fazia fundos atrasados sumirem INTEIRAMENTE da lista mesmo ainda muito
    provavelmente segurando a posicao (confirmado 12/jul/2026: fundo
    ZUCCHERO RV so tem CDA ate 03/2026 pra SMTO3, sumia da lista mesmo
    concentrando ~98% do PL dele nesse ativo). Janela de
    STALE_HOLDER_LOOKBACK_DAYS evita trazer fundo genuinamente inativo ha
    muito tempo. `ref_date` explicito continua pegando o snapshot exato
    daquele mes, sem essa logica de "ultimo disponivel".

    `include_closed=True` (equivalente ao "Exibir Zeradas" do layout de
    referencia) tambem inclui fundos cuja ULTIMA movimentacao nesse ativo
    foi um zeramento (classification=CLOSED) — eles nao tem mais linha em
    fund_holdings (posicao=0 nao fica guardada la), entao vem do proprio
    FundAssetMovement, com quantity/market_value=0."""
    if ref_date is not None:
        stmt = (
            select(FundHolding, Fund.name, Fund.cnpj, FundAssetMovement.classification, FundAssetMovement.qty_delta)
            .join(Fund, Fund.id == FundHolding.fund_id)
            .outerjoin(
                FundAssetMovement,
                (FundAssetMovement.fund_id == FundHolding.fund_id)
                & (FundAssetMovement.asset_id == FundHolding.asset_id)
                & (FundAssetMovement.ref_date == FundHolding.ref_date),
            )
            .where(FundHolding.asset_id == asset_id, FundHolding.ref_date == ref_date)
        )
        rows = db.execute(stmt).all()
        holder_data = [(h.fund_id, name, cnpj, h.ref_date, float(h.quantity), float(h.market_value), classification, qty_delta) for h, name, cnpj, classification, qty_delta in rows]
    else:
        cutoff = date.today() - timedelta(days=STALE_HOLDER_LOOKBACK_DAYS)
        latest_per_fund = (
            select(FundHolding.fund_id, func.max(FundHolding.ref_date).label("ref_date"))
            .where(FundHolding.asset_id == asset_id, FundHolding.ref_date >= cutoff)
            .group_by(FundHolding.fund_id)
            .subquery()
        )
        stmt = (
            select(FundHolding, Fund.name, Fund.cnpj, FundAssetMovement.classification, FundAssetMovement.qty_delta)
            .join(Fund, Fund.id == FundHolding.fund_id)
            .join(
                latest_per_fund,
                (latest_per_fund.c.fund_id == FundHolding.fund_id) & (latest_per_fund.c.ref_date == FundHolding.ref_date),
            )
            .outerjoin(
                FundAssetMovement,
                (FundAssetMovement.fund_id == FundHolding.fund_id)
                & (FundAssetMovement.asset_id == FundHolding.asset_id)
                & (FundAssetMovement.ref_date == FundHolding.ref_date),
            )
            .where(FundHolding.asset_id == asset_id)
        )
        rows = db.execute(stmt).all()
        holder_data = [(h.fund_id, name, cnpj, h.ref_date, float(h.quantity), float(h.market_value), classification, qty_delta) for h, name, cnpj, classification, qty_delta in rows]

        if include_closed:
            current_fund_ids = {r[0] for r in holder_data}
            latest_movement_per_fund = (
                select(FundAssetMovement.fund_id, func.max(FundAssetMovement.ref_date).label("ref_date"))
                .where(FundAssetMovement.asset_id == asset_id, FundAssetMovement.ref_date >= cutoff)
                .group_by(FundAssetMovement.fund_id)
                .subquery()
            )
            closed_stmt = (
                select(FundAssetMovement, Fund.name, Fund.cnpj)
                .join(Fund, Fund.id == FundAssetMovement.fund_id)
                .join(
                    latest_movement_per_fund,
                    (latest_movement_per_fund.c.fund_id == FundAssetMovement.fund_id)
                    & (latest_movement_per_fund.c.ref_date == FundAssetMovement.ref_date),
                )
                .where(FundAssetMovement.asset_id == asset_id, FundAssetMovement.classification == MovementClassification.CLOSED)
            )
            for m, name, cnpj in db.execute(closed_stmt).all():
                if m.fund_id in current_fund_ids:
                    continue  # fundo zerou e depois recomprou dentro da janela — ja esta em holder_data com qty>0
                holder_data.append((m.fund_id, name, cnpj, m.ref_date, 0.0, 0.0, m.classification, float(m.qty_delta)))

    # Patrimonio do fundo, pra calcular "% do PL" — fonte PRINCIPAL agora e'
    # FundNav (campo VL_PATRIM_LIQ do arquivo PL_ dentro do MESMO zip da CDA,
    # mesma competencia/CNPJ_FUNDO_CLASSE da posicao), nao mais FundQuota
    # (Informe Diario, dataset SEPARADO). Achado 12/jul/2026 comparando
    # SMFT3 x CarteiraFundos.com: GENERALE FIF aparecia com %PL errado
    # (107% via Informe Diario, com toda uma bateria de filtros de
    # plausibilidade pra chegar nesse numero) quando o certo, usando o
    # patrimonio da PROPRIA CDA daquele mes, e' 318,9% — batendo quase exato
    # com a referencia (~320%). FIPs (private equity) tambem passam a
    # aparecer, porque reportam PL na propria CDA mesmo sem Informe Diario
    # diario (FIP nao tem cota de liquidez diaria). Cobertura de FundNav:
    # 100% dos periodos 2023+ (mesmo pipeline/arquivo que FundHolding), so
    # ~9% pre-2023 (backfill historico do CDA_HIST ainda nao tem o PL_
    # completo pra esses anos) — fallback abaixo cobre esse gap.
    fund_ids = list({fund_id for fund_id, *_ in holder_data})
    nav_by_fund_date: dict[tuple[int, date], float] = {}
    navs_by_fund: dict[int, list[FundNav]] = {}
    if fund_ids:
        nav_rows = db.execute(
            select(FundNav).where(FundNav.fund_id.in_(fund_ids)).order_by(FundNav.fund_id, FundNav.ref_date)
        ).scalars()
        for n in nav_rows:
            if (n.fund_id, n.ref_date) in KNOWN_BAD_NAV_POINTS:
                continue
            nav_by_fund_date[(n.fund_id, n.ref_date)] = float(n.net_asset_value)
            navs_by_fund.setdefault(n.fund_id, []).append(n)

    # Fallback pra quando FundNav nao cobre o periodo (essencialmente so
    # pre-2023) — mesma logica de plausibilidade validada antes (piso de
    # posicao/carteira com folga de alavancagem e ruido de marcacao), agora
    # so usada como segunda linha, nao mais a fonte principal.
    quotas_by_fund: dict[int, list[FundQuota]] = {}
    portfolio_totals: dict[tuple[int, date], float] = {}
    if fund_ids:
        quota_rows = db.execute(
            select(FundQuota).where(FundQuota.fund_id.in_(fund_ids)).order_by(FundQuota.fund_id, FundQuota.ref_date)
        ).scalars()
        for q in quota_rows:
            quotas_by_fund.setdefault(q.fund_id, []).append(q)
        portfolio_rows = db.execute(
            select(FundHolding.fund_id, FundHolding.ref_date, func.sum(FundHolding.market_value))
            .where(FundHolding.fund_id.in_(fund_ids))
            .group_by(FundHolding.fund_id, FundHolding.ref_date)
        ).all()
        for fid, rd, total in portfolio_rows:
            portfolio_totals[(fid, rd)] = float(total)

    # navs/quotas em (date, float) ordenado — formato que app.services.nav_lookup
    # espera. Mantem navs_by_fund/quotas_by_fund (objetos ORM) so pra
    # n_shareholders_as_of, que precisa de campos que o helper compartilhado
    # nao carrega.
    navs_f_by_fund: dict[int, list[tuple[date, float]]] = {
        fid: [(n.ref_date, float(n.net_asset_value)) for n in navs] for fid, navs in navs_by_fund.items()
    }
    quotas_f_by_fund: dict[int, list[tuple[date, float]]] = {
        fid: [(q.ref_date, float(q.net_asset_value)) for q in quotas] for fid, quotas in quotas_by_fund.items()
    }

    def quota_fallback(fund_id: int, holding_date: date, position_value: float) -> float | None:
        portfolio_total = portfolio_totals.get((fund_id, holding_date), 0.0)
        return nav_lookup.quota_fallback(holding_date, position_value, portfolio_total, quotas_f_by_fund.get(fund_id, []))

    def nav_as_of(fund_id: int, holding_date: date) -> float | None:
        portfolio_total = portfolio_totals.get((fund_id, holding_date), 0.0)
        exact = nav_by_fund_date.get((fund_id, holding_date))
        return nav_lookup.nav_as_of(holding_date, portfolio_total, exact, navs_f_by_fund.get(fund_id, []))

    def n_shareholders_as_of(fund_id: int, holding_date: date) -> int | None:
        # So informativo (nao entra na conta de %PL, que agora usa FundNav) —
        # FundNav nao tem contagem de cotistas, entao continua vindo do
        # Informe Diario, sem filtro de plausibilidade (nao afeta nenhum
        # calculo, so exibicao).
        best = None
        for q in quotas_by_fund.get(fund_id, []):
            if q.ref_date > holding_date:
                break
            best = q
        return best.n_shareholders if best else None

    # Preco da acao na epoca de cada posicao — pedido do usuario 15/jul/2026
    # ("preco da acao qual o fundo adicionou/reduziu/zerou, se tiver essa
    # informacao"). A CDA nao traz preco de negociacao (so' valor de mercado
    # da posicao inteira), entao usa o fechamento real da B3 (COTAHIST, ja
    # ingerido pra Insiders/Recompras/Evolucao) no pregao mais proximo <=
    # ref_date — nao e' o preco que o fundo pagou de fato (a CDA nunca traz
    # isso), so' a cotacao de mercado vigente naquele mes.
    asset_ticker = db.execute(select(Asset.ticker).where(Asset.id == asset_id)).scalar_one_or_none()
    prices_sorted: list[tuple[date, float]] = []
    if asset_ticker:
        price_rows = db.execute(
            select(AssetPriceHistory.trade_date, AssetPriceHistory.close)
            .where(AssetPriceHistory.ticker == asset_ticker)
            .order_by(AssetPriceHistory.trade_date)
        ).all()
        prices_sorted = [(r.trade_date, float(r.close)) for r in price_rows]

    def price_as_of(holding_date: date) -> float | None:
        best = None
        for d, price in prices_sorted:
            if d > holding_date:
                break
            best = price
        return best

    results = []
    for fund_id, name, cnpj, h_ref_date, quantity, market_value, classification, qty_delta in holder_data:
        nav = nav_as_of(fund_id, h_ref_date)
        if nav is None:
            nav = quota_fallback(fund_id, h_ref_date, market_value)
        results.append(
            AssetHolderOut(
                fund_id=fund_id,
                fund_name=name,
                fund_cnpj=cnpj,
                quantity=quantity,
                market_value=market_value,
                classification=classification.value if classification else None,
                qty_delta=float(qty_delta) if qty_delta is not None else None,
                ref_date=h_ref_date,
                fund_net_asset_value=nav,
                fund_n_shareholders=n_shareholders_as_of(fund_id, h_ref_date),
                price_at_ref_date=price_as_of(h_ref_date),
            )
        )
    results.sort(key=lambda r: r.market_value, reverse=True)
    return results


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
