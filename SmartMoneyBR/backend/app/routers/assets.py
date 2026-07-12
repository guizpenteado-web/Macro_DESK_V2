from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Fund, FundAssetMovement, FundHolding, FundQuota, MovementClassification
from app.schemas.asset import AssetHolderOut, AssetOut, AssetTimelinePoint
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

    # Patrimonio/cotistas do fundo como um todo (nao so a posicao neste ativo).
    # Cada holding agora pode ter seu PROPRIO ref_date (fundos atrasados
    # mostram a ultima posicao que declararam, ver acima) — o patrimonio
    # tem que ser da MESMA epoca da posicao, senao a % fica errada (ex:
    # posicao de marco / patrimonio de junho, meses depois, %  incoerente).
    # Por fundo, pega TODAS as quotas e escolhe a mais recente <= ref_date
    # da posicao (nao a mais recente global do fundo).
    fund_ids = list({fund_id for fund_id, *_ in holder_data})
    quotas_by_fund: dict[int, list[FundQuota]] = {}
    if fund_ids:
        quota_rows = db.execute(
            select(FundQuota).where(FundQuota.fund_id.in_(fund_ids)).order_by(FundQuota.fund_id, FundQuota.ref_date)
        ).scalars()
        for q in quota_rows:
            quotas_by_fund.setdefault(q.fund_id, []).append(q)

    # Patrimonio total da carteira do fundo (soma de TODOS os ativos, nao so
    # o que estamos exibindo) por (fund_id, ref_date) — usado como piso mais
    # forte que so a posicao individual (ver quota_as_of abaixo). Achado
    # 12/jul/2026 (MULT3 x KINEA ATLAS II): o piso de "posicao unica" nao
    # pega o caso em que NENHUMA posicao isolada excede o patrimonio
    # informado, mas a carteira INTEIRA do fundo (109 ativos, R$294mi) excede
    # um patrimonio residual de R$2,8mi do mesmo mes — mesma anomalia da
    # fonte, so que dessa vez distribuida entre varias posicoes pequenas.
    portfolio_totals: dict[tuple[int, date], float] = {}
    if fund_ids:
        portfolio_rows = db.execute(
            select(FundHolding.fund_id, FundHolding.ref_date, func.sum(FundHolding.market_value))
            .where(FundHolding.fund_id.in_(fund_ids))
            .group_by(FundHolding.fund_id, FundHolding.ref_date)
        ).all()
        for fid, rd, total in portfolio_rows:
            portfolio_totals[(fid, rd)] = float(total)

    # Fundos multimercado podem legitimamente ter notional em acoes MAIOR que
    # o patrimonio (derivativos/margem) — achado 12/jul/2026 (VISTA ON ACCESS
    # em MULT3): razao carteira/patrimonio ~1.4-1.8x em TODOS os meses
    # disponiveis, estavel, sem nenhum salto — alavancagem real, nao dado
    # corrompido. Uma margem generosa (5x) ainda barra o caso degenerado
    # (KINEA ATLAS II: razao ~100x num unico mes residual) sem esconder
    # posicao legitima de fundo alavancado.
    PORTFOLIO_TO_NAV_MAX_RATIO = 5.0
    # Tolerancia pra ruido normal de data de marcacao entre a posicao (CDA,
    # fechamento do mes) e a cota (Informe Diario, pode ser marcada num dia
    # util ligeiramente diferente) — achado 12/jul/2026 numa auditoria
    # ampla (todos os ativos, nao so MULT3): fundos como MAKO INR II e HAWK
    # II FIF EM ACOES tem carteira e patrimonio andando juntos o tempo todo
    # (mesma tendencia, mesma ordem de grandeza), so que a posicao vem 1-5%
    # ACIMA do patrimonio registrado nesse mes especifico por puro
    # descompasso de marcacao — nao e' o padrao "residual" nem alavancagem,
    # e o piso estrito (1.0x) rejeitava TODAS as cotas do fundo sem excecao
    # (carteira sempre ligeiramente a frente da cota), zerando o %PL de um
    # fundo com dado perfeitamente normal. 10% cobre esse ruido sem abrir
    # espaco pro caso residual de verdade (que salta 100x+, nao 1-5%).
    FLOOR_TOLERANCE = 1.10

    def quota_as_of(fund_id: int, holding_date: date, position_value: float) -> FundQuota | None:
        # Pula qualquer quota onde o patrimonio do fundo inteiro sai MENOR
        # que essa unica posicao em acoes (nunca plausivel, nem alavancado —
        # seria uma posicao maior que o fundo inteiro) OU muito menor que a
        # soma de TODA a carteira conhecida (alem da margem de alavancagem
        # acima) — sinal claro de dado inconsistente do Informe Diario nesse
        # mes especifico (confirmado 12/jul/2026: alguns fundos
        # "espelho"/master alternam entre patrimonio real e um residual de
        # ~R$1-2mi com 1 cotista, mes sim mes nao, sem motivo aparente na
        # fonte — nao e' bug de parsing nosso). Continua a procura mais pra
        # tras ate achar uma quota plausivel.
        portfolio_total = portfolio_totals.get((fund_id, holding_date), 0.0)
        best = None
        for q in quotas_by_fund.get(fund_id, []):
            if q.ref_date > holding_date:
                break
            nav = float(q.net_asset_value)
            if position_value > 0 and nav * FLOOR_TOLERANCE < position_value:
                continue
            if portfolio_total > 0 and nav * PORTFOLIO_TO_NAV_MAX_RATIO < portfolio_total:
                continue
            best = q
        return best

    results = []
    for fund_id, name, cnpj, h_ref_date, quantity, market_value, classification, qty_delta in holder_data:
        q = quota_as_of(fund_id, h_ref_date, market_value)
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
                fund_net_asset_value=float(q.net_asset_value) if q else None,
                fund_n_shareholders=q.n_shareholders if q else None,
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
