"""Motor de alertas — escaneia tabelas que ja existem (recompra, insider,
movimentacao de fundos) e gera eventos notaveis. Nao ingere nada de fora;
roda depois de cada job de ingestao. Idempotente via `dedupe_key` derivado
dos dados de origem — reprocessar nunca duplica o mesmo alerta
(on_conflict_do_nothing na constraint unica de Alert.dedupe_key)."""
from __future__ import annotations

import logging
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Alert, Asset, CompanyBuyback, Fund, FundAssetMovement, InsiderTrade, MovementClassification

logger = logging.getLogger(__name__)


def _upsert_alerts(db: Session, rows: list[dict]) -> int:
    if not rows:
        return 0
    stmt = pg_insert(Alert).values(rows).on_conflict_do_nothing(index_elements=["dedupe_key"])
    result = db.execute(stmt)
    db.commit()
    return result.rowcount or 0


def generate_buyback_alerts(db: Session, lookback_days: int = 30) -> int:
    """Novo programa de recompra declarado nos ultimos N dias."""
    since = date.today() - timedelta(days=lookback_days)
    programs = db.execute(select(CompanyBuyback).where(CompanyBuyback.declared_at >= since)).scalars().all()
    rows = [
        {
            "type": "buyback_new",
            "severity": "info",
            "title": f"{p.company_name} declarou programa de recompra",
            "message": (
                f"{(p.qty_common_shares or 0):,.0f} ações ON + {(p.qty_preferred_shares or 0):,.0f} ações PN "
                f"autorizadas. Prazo final: {p.deadline}."
            ),
            "entity_type": "company",
            "entity_id": p.id,
            "ref_date": p.declared_at,
            "dedupe_key": f"buyback:{p.id}",
        }
        for p in programs
    ]
    return _upsert_alerts(db, rows)


def generate_insider_alerts(db: Session, lookback_days: int = 30, min_volume: float = 100_000) -> int:
    """Compra relevante de insider (Conselho/Diretor/Controlador) nos
    últimos N dias, acima de um volume mínimo — evita alerta pra lotes
    residuais de plano de remuneração a custo zero."""
    since = date.today() - timedelta(days=lookback_days)
    trades = (
        db.execute(
            select(InsiderTrade).where(
                InsiderTrade.direction == "COMPRA",
                InsiderTrade.data_movimentacao >= since,
                InsiderTrade.volume >= min_volume,
            )
        )
        .scalars()
        .all()
    )
    rows = [
        {
            "type": "insider_buy",
            "severity": "success",
            "title": f"{t.tipo_cargo or 'Insider'} comprou ações de {t.company_name}",
            "message": (
                f"{(t.quantidade or 0):,.0f} {t.tipo_ativo or 'ações'} a R$ {(t.preco_unitario or 0):,.2f} "
                f"(R$ {(t.volume or 0):,.0f})."
            ),
            "entity_type": "company",
            "entity_id": None,
            "ref_date": t.data_movimentacao,
            "dedupe_key": f"insider:{t.cnpj_companhia}:{t.data_movimentacao}:{t.tipo_cargo}:{t.empresa}:{t.quantidade}:{t.preco_unitario}",
        }
        for t in trades
    ]
    return _upsert_alerts(db, rows)


def generate_fund_reopened_alerts(db: Session, lookback_days: int = 30) -> int:
    """Fundo reabriu uma posição que tinha zerado antes: toda movimentação
    NEW recente onde o MESMO par (fundo, ativo) já teve uma CLOSED em algum
    mês anterior."""
    since = date.today() - timedelta(days=lookback_days)
    new_moves = db.execute(
        select(FundAssetMovement, Fund.name, Asset.ticker)
        .join(Fund, Fund.id == FundAssetMovement.fund_id)
        .join(Asset, Asset.id == FundAssetMovement.asset_id)
        .where(FundAssetMovement.classification == MovementClassification.NEW, FundAssetMovement.ref_date >= since)
    ).all()

    rows = []
    for m, fund_name, ticker in new_moves:
        had_closed = db.execute(
            select(FundAssetMovement.id)
            .where(
                FundAssetMovement.fund_id == m.fund_id,
                FundAssetMovement.asset_id == m.asset_id,
                FundAssetMovement.classification == MovementClassification.CLOSED,
                FundAssetMovement.ref_date < m.ref_date,
            )
            .limit(1)
        ).scalar_one_or_none()
        if had_closed is None:
            continue
        rows.append(
            {
                "type": "fund_reopened",
                "severity": "info",
                "title": f"{fund_name} reabriu posição em {ticker}",
                "message": f"Tinha zerado essa posição antes e voltou a comprar em {m.ref_date} — R$ {float(m.value_delta):,.0f}.",
                "entity_type": "fund",
                "entity_id": m.fund_id,
                "ref_date": m.ref_date,
                "dedupe_key": f"reopen:{m.fund_id}:{m.asset_id}:{m.ref_date}",
            }
        )
    return _upsert_alerts(db, rows)


def generate_all_alerts(db: Session) -> dict[str, int]:
    return {
        "buyback_new": generate_buyback_alerts(db),
        "insider_buy": generate_insider_alerts(db),
        "fund_reopened": generate_fund_reopened_alerts(db),
    }
