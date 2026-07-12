"""Top-performers ranking (real investment return via quota value) and the
detailed per-fund performance breakdown requested by the user: principais
alteracoes, evolucao de posicoes compradas, top compras, o que aumentou/
diminuiu — all with % relative to the prior position.
"""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Asset, Fund, FundAssetMovement, FundHolding, FundQuota, MovementClassification
from app.services.returns import REBASE_RATIO_HIGH, REBASE_RATIO_LOW, compute_window_return

router = APIRouter(prefix="/api", tags=["performance"])


@router.get("/rankings/top-performers")
def top_performers(years: int = Query(20, ge=1, le=26), limit: int = 20, db: Session = Depends(get_db)):
    """Top N funds by REAL return (quota value growth), restricted to funds
    that hold at least one equity position (so clicking through always leads
    to a fund page with actual holdings/movements to show)."""
    max_date = db.execute(select(func.max(FundQuota.ref_date))).scalar_one_or_none()
    if max_date is None:
        return {"window_years": years, "as_of": None, "rows": []}

    window_start = date(max_date.year - years, max_date.month, 1)

    equity_fund_ids = select(FundHolding.fund_id).distinct().subquery()

    # Full quota history from window_start on, per equity fund — needed (not
    # just first/last) so compute_window_return can detect quota rebases
    # (see app/services/returns.py) instead of blindly dividing last/first.
    quota_rows = db.execute(
        select(FundQuota.fund_id, FundQuota.ref_date, FundQuota.quota_value)
        .where(FundQuota.ref_date >= window_start, FundQuota.fund_id.in_(select(equity_fund_ids.c.fund_id)))
        .order_by(FundQuota.fund_id, FundQuota.ref_date)
    ).all()

    last_quota_row = db.execute(
        select(
            FundQuota.fund_id,
            FundQuota.ref_date,
            FundQuota.net_asset_value,
            FundQuota.n_shareholders,
        ).where(FundQuota.ref_date == max_date)
    ).all()
    last_quota = {r.fund_id: r for r in last_quota_row}

    series_by_fund: dict[int, list[tuple[date, float]]] = {}
    for r in quota_rows:
        series_by_fund.setdefault(r.fund_id, []).append((r.ref_date, float(r.quota_value)))

    results = []
    for fund_id, series in series_by_fund.items():
        if fund_id not in last_quota:
            continue
        pct_return, first_date = compute_window_return(series, window_start)
        if pct_return is None:
            continue
        last_row = last_quota[fund_id]
        # Require a reasonably long clean track record so a fund that only
        # just launched (or was just rebased) doesn't look like a "20-year return".
        if (last_row.ref_date - first_date).days < 30:
            continue
        results.append(
            {
                "fund_id": fund_id,
                "first_date": first_date,
                "last_date": last_row.ref_date,
                "pct_return": pct_return,
                "net_asset_value": float(last_row.net_asset_value) if last_row.net_asset_value is not None else None,
                "n_shareholders": last_row.n_shareholders,
            }
        )

    results.sort(key=lambda x: x["pct_return"], reverse=True)
    top = results[:limit]

    fund_ids = [t["fund_id"] for t in top]
    funds_by_id = {f.id: f for f in db.execute(select(Fund).where(Fund.id.in_(fund_ids))).scalars()} if fund_ids else {}

    rows = [
        {
            "fund_id": t["fund_id"],
            "fund_name": funds_by_id[t["fund_id"]].name if t["fund_id"] in funds_by_id else None,
            "fund_cnpj": funds_by_id[t["fund_id"]].cnpj if t["fund_id"] in funds_by_id else None,
            "pct_return": round(t["pct_return"], 2),
            "first_date": t["first_date"],
            "last_date": t["last_date"],
            "net_asset_value": t["net_asset_value"],
            "n_shareholders": t["n_shareholders"],
            "financials_ref_date": t["last_date"],
        }
        for t in top
    ]

    return {"window_years": years, "as_of": max_date, "rows": rows}


@router.get("/evolution/flow")
def flow_evolution(db: Session = Depends(get_db)):
    """Agregado de TODOS os fundos, mes a mes: valor total investido em
    posicoes NEW/INCREASED (mesma metrica de 'evolucao_posicoes_compradas'
    de um fundo, so que somada entre todos) + numero de fundos distintos que
    compraram naquele mes (breadth). O insight pedido: nao basta um valor
    agregado alto — se e so 1-2 fundos grandes comprando, nao e 'todo mundo
    comprando junto'. coordination_score combina as duas dimensoes (valor
    ACIMA da media × fundos ACIMA da media) pra achar os meses onde ambas
    coincidiram, que e o sinal real de fluxo institucional coordenado."""
    # O primeiro mes com dado (CDA comeca em 2024-07) e um artefato: TODO
    # fundo aparece como NEW nesse mes so porque nao existe mes anterior pra
    # comparar (nao tem prior_ref_date) — nao e sinal real de compra
    # coordenada, e 100% dos fundos "comprando" de uma vez por definicao.
    # Confirmado nos dados reais (10/jul/2026): pct_funds_buying=1.0 so nesse
    # mes. Excluido da analise.
    first_ref_date = db.execute(select(func.min(FundAssetMovement.ref_date))).scalar_one_or_none()

    rows = db.execute(
        select(
            FundAssetMovement.ref_date,
            func.sum(FundAssetMovement.value_delta).label("total_value_bought"),
            func.count(func.distinct(FundAssetMovement.fund_id)).label("n_funds_buying"),
        )
        .where(
            FundAssetMovement.classification.in_([MovementClassification.NEW, MovementClassification.INCREASED]),
            FundAssetMovement.ref_date != first_ref_date,
        )
        .group_by(FundAssetMovement.ref_date)
        .order_by(FundAssetMovement.ref_date)
    ).all()

    active_rows = db.execute(
        select(FundAssetMovement.ref_date, func.count(func.distinct(FundAssetMovement.fund_id)).label("n_funds_active"))
        .group_by(FundAssetMovement.ref_date)
    ).all()
    active_by_date = {r.ref_date: r.n_funds_active for r in active_rows}

    if not rows:
        return {"months": [], "avg_total_value_bought": None, "avg_n_funds_buying": None}

    avg_value = sum(float(r.total_value_bought) for r in rows) / len(rows)
    avg_n_funds = sum(r.n_funds_buying for r in rows) / len(rows)

    months = []
    for r in rows:
        total_value = float(r.total_value_bought)
        n_funds_active = active_by_date.get(r.ref_date, 0)
        value_vs_avg = (total_value / avg_value) if avg_value else 0.0
        funds_vs_avg = (r.n_funds_buying / avg_n_funds) if avg_n_funds else 0.0
        months.append(
            {
                "ref_date": r.ref_date,
                "total_value_bought": total_value,
                "n_funds_buying": r.n_funds_buying,
                "n_funds_active": n_funds_active,
                "pct_funds_buying": (r.n_funds_buying / n_funds_active) if n_funds_active else None,
                "value_vs_avg": value_vs_avg,
                "funds_vs_avg": funds_vs_avg,
                "coordination_score": value_vs_avg * funds_vs_avg,
            }
        )

    return {"months": months, "avg_total_value_bought": avg_value, "avg_n_funds_buying": avg_n_funds}


@router.get("/funds/{fund_id}/quota-history")
def fund_quota_history(fund_id: int, years: int = Query(20, ge=1, le=26), db: Session = Depends(get_db)):
    """Serie historica de valor de cota (indexada a 100 no inicio) para o
    grafico de 'cotacao' do fundo. Reusa a mesma logica de deteccao de rebase
    de app/services/returns.py — se houver uma restruturacao/amortizacao no
    meio da janela, a serie e' cortada para comecar logo apos o ultimo
    rebase, em vez de mostrar um salto vertical sem sentido no grafico."""
    max_date = db.execute(select(func.max(FundQuota.ref_date)).where(FundQuota.fund_id == fund_id)).scalar_one_or_none()
    if max_date is None:
        return {"points": [], "window_start": None}

    window_start = date(max_date.year - years, max_date.month, 1)
    rows = db.execute(
        select(FundQuota.ref_date, FundQuota.quota_value)
        .where(FundQuota.fund_id == fund_id, FundQuota.ref_date >= window_start)
        .order_by(FundQuota.ref_date)
    ).all()
    series = [(r.ref_date, float(r.quota_value)) for r in rows]
    if len(series) < 2:
        return {"points": [], "window_start": None}

    effective_start_idx = 0
    for i in range(1, len(series)):
        prev_v = series[i - 1][1]
        cur_v = series[i][1]
        if prev_v <= 0:
            continue
        ratio = cur_v / prev_v
        if ratio > REBASE_RATIO_HIGH or ratio < REBASE_RATIO_LOW:
            effective_start_idx = i

    clean = series[effective_start_idx:]
    base_value = clean[0][1]
    points = [
        {"ref_date": d, "quota_value": v, "indexed": (v / base_value) * 100 if base_value else None}
        for d, v in clean
    ]
    return {"points": points, "window_start": clean[0][0]}


@router.get("/funds/{fund_id}/performance")
def fund_performance(fund_id: int, ref_date: date | None = None, top_n: int = 10, db: Session = Depends(get_db)):
    """Dedicated breakdown for the fund performance page: ultimas
    movimentacoes, principais alteracoes, top compras, o que aumentou/
    diminuiu, e evolucao mensal de posicoes compradas — tudo com % relativo
    a posicao anterior (pct_delta, ja calculado pelo motor de comparacao)."""
    target_date = ref_date
    if target_date is None:
        target_date = db.execute(select(func.max(FundAssetMovement.ref_date)).where(FundAssetMovement.fund_id == fund_id)).scalar_one_or_none()
    if target_date is None:
        return {"ref_date": None, "movements": [], "top_bought": [], "increased": [], "decreased": [], "monthly_bought_evolution": []}

    rows = db.execute(
        select(FundAssetMovement, Asset.ticker, Asset.company_name)
        .join(Asset, Asset.id == FundAssetMovement.asset_id)
        .where(FundAssetMovement.fund_id == fund_id, FundAssetMovement.ref_date == target_date)
    ).all()

    # Mesmo denominador da aba "Carteira atual" (pct_of_equity_book em
    # funds.py) — soma do valor de mercado de TODAS as posicoes do fundo
    # nesse ref_date, nao so as que tiveram movimentacao. Da o peso real de
    # cada alteracao no book, nao so o % de crescimento da posicao em si
    # (que o pct_delta ja mostra).
    total_equities = db.execute(
        select(func.sum(FundHolding.market_value)).where(FundHolding.fund_id == fund_id, FundHolding.ref_date == target_date)
    ).scalar_one_or_none()
    total_equities = float(total_equities) if total_equities else None

    def to_dict(m: FundAssetMovement, ticker: str, company_name: str | None) -> dict:
        # Zeragem zera value_current por definicao — usar value_prior pra
        # mostrar quanto essa posicao pesava no book antes de ser fechada,
        # em vez de um "0%" sem informacao nenhuma.
        weight_value = float(m.value_prior) if m.classification == MovementClassification.CLOSED else float(m.value_current)
        return {
            "asset_id": m.asset_id,
            "ticker": ticker,
            "company_name": company_name,
            "classification": m.classification.value,
            "qty_current": float(m.qty_current),
            "qty_prior": float(m.qty_prior),
            "qty_delta": float(m.qty_delta),
            "value_current": float(m.value_current),
            "value_delta": float(m.value_delta),
            "pct_delta": float(m.pct_delta) if m.pct_delta is not None else None,
            "pct_of_equity_book": (weight_value / total_equities * 100) if total_equities else None,
        }

    movements = [to_dict(m, t, c) for m, t, c in rows]
    movements.sort(key=lambda x: abs(x["value_delta"]), reverse=True)

    increased = [m for m in movements if m["classification"] in ("NEW", "INCREASED")]
    decreased = [m for m in movements if m["classification"] in ("DECREASED", "CLOSED")]
    top_bought = sorted(increased, key=lambda x: x["value_delta"], reverse=True)[:top_n]
    top_decreased = sorted(decreased, key=lambda x: x["value_delta"])[:top_n]

    # Evolucao mensal de posicoes compradas: valor total investido em posicoes
    # NEW/INCREASED, mes a mes, para visualizar a trajetoria de "compras" do
    # fundo ao longo do tempo (nao so o mes atual).
    evo_rows = db.execute(
        select(
            FundAssetMovement.ref_date,
            func.sum(FundAssetMovement.value_delta).label("total_bought"),
            func.count().label("n_positions"),
        )
        .where(
            FundAssetMovement.fund_id == fund_id,
            FundAssetMovement.classification.in_([MovementClassification.NEW, MovementClassification.INCREASED]),
        )
        .group_by(FundAssetMovement.ref_date)
        .order_by(FundAssetMovement.ref_date)
    ).all()

    return {
        "ref_date": target_date,
        "principais_alteracoes": movements[:top_n],
        "top_posicoes_compradas": top_bought,
        "o_que_aumentou": [m for m in increased if m["classification"] == "INCREASED"],
        "o_que_diminuiu": [m for m in decreased if m["classification"] == "DECREASED"],
        "novas_posicoes": [m for m in increased if m["classification"] == "NEW"],
        "zeragens": [m for m in decreased if m["classification"] == "CLOSED"],
        "evolucao_posicoes_compradas": [
            {"ref_date": r.ref_date, "total_bought": float(r.total_bought), "n_positions": r.n_positions} for r in evo_rows
        ],
    }
