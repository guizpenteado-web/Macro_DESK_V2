"""CDA (Composicao e Diversificacao das Aplicacoes) ingestion — equities only.

See docs/DATA_SOURCES.md for the verified facts this module relies on:
- one zip per competencia month, uniform structure across all history tested
- BLC_4 mixes equities with debentures/options/futures/BDRs — must filter by
  TP_ATIVO, not TP_APLIC
- the same ticker can appear twice for the same fund+month (held vs. lent out
  under securities lending) — must be summed, not just deduped
- decimal separator is a period, not a comma
- PL file (net asset value) comes free in the same zip
"""
from __future__ import annotations

import io
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Asset, Fund, FundHolding, FundNav, IngestionLog
from app.services.cvm_client import download_cda_zip, extract_member
from app.utils.dates import yyyymm_to_ref_date_end_of_month

logger = logging.getLogger(__name__)

# Verified against real data (see docs/DATA_SOURCES.md) — units like KLBN11
# fall under "Certificado de deposito de acoes", NOT "Acao ordinaria/preferencial".
EQUITY_TP_ATIVO = {
    "Ação ordinária",
    "Ação preferencial",
    "Certificado de depósito de ações",
}

# BDRs (Brazilian Depositary Receipts — B3-listed receipts over foreign
# shares, e.g. AAPL34). Verified against real BLC_4 data (2026-06): 5 distinct
# TP_ATIVO values, ~5.4k rows/month total — same order of magnitude as
# "Certificado de deposito de acoes" (5.3k), not a rounding error to ignore.
# Added 10/jul/2026 at user's request.
BDR_TP_ATIVO = {
    "BDR não patrocinado",
    "BDR nível I",
    "BDR nível II",
    "BDR nível III",
    "BDR de ETF",
}

TRACKED_TP_ATIVO = EQUITY_TP_ATIVO | BDR_TP_ATIVO

BLC4_COLUMNS = [
    "CNPJ_FUNDO_CLASSE",
    "DENOM_SOCIAL",
    "TP_FUNDO_CLASSE",
    "DT_COMPTC",
    "TP_ATIVO",
    "CD_ATIVO",
    "DS_ATIVO",
    "CD_ISIN",
    "QT_POS_FINAL",
    "VL_MERC_POS_FINAL",
]

PL_COLUMNS = ["CNPJ_FUNDO_CLASSE", "DENOM_SOCIAL", "TP_FUNDO_CLASSE", "DT_COMPTC", "VL_PATRIM_LIQ"]


def _read_csv(raw: bytes, usecols: list[str]) -> pd.DataFrame:
    return pd.read_csv(io.BytesIO(raw), sep=";", encoding="latin-1", usecols=usecols, low_memory=False)


def parse_equities(zip_path) -> pd.DataFrame:
    raw = extract_member(zip_path, f"BLC_4_{zip_path.stem.split('_')[-1]}.csv")
    if raw is None:
        raise FileNotFoundError(f"BLC_4 nao encontrado em {zip_path}")

    df = _read_csv(raw, BLC4_COLUMNS)
    df = df[df["TP_ATIVO"].isin(TRACKED_TP_ATIVO)].copy()

    # Same fund+ticker+month can appear more than once (e.g. held position +
    # position lent out under securities lending) — consolidate into one row.
    grouped = (
        df.groupby(["CNPJ_FUNDO_CLASSE", "CD_ATIVO", "DT_COMPTC"], as_index=False)
        .agg(
            QT_POS_FINAL=("QT_POS_FINAL", "sum"),
            VL_MERC_POS_FINAL=("VL_MERC_POS_FINAL", "sum"),
            DENOM_SOCIAL=("DENOM_SOCIAL", "first"),
            TP_FUNDO_CLASSE=("TP_FUNDO_CLASSE", "first"),
            DS_ATIVO=("DS_ATIVO", "first"),
            CD_ISIN=("CD_ISIN", "first"),
            TP_ATIVO=("TP_ATIVO", "first"),
        )
    )
    return grouped


def parse_nav(zip_path) -> pd.DataFrame:
    raw = extract_member(zip_path, f"PL_{zip_path.stem.split('_')[-1]}.csv")
    if raw is None:
        raise FileNotFoundError(f"PL nao encontrado em {zip_path}")
    return _read_csv(raw, PL_COLUMNS)


def _upsert_funds(db: Session, df: pd.DataFrame) -> dict[str, int]:
    dims = df[["CNPJ_FUNDO_CLASSE", "DENOM_SOCIAL", "TP_FUNDO_CLASSE"]].drop_duplicates("CNPJ_FUNDO_CLASSE")
    rows = [
        {"cnpj": r.CNPJ_FUNDO_CLASSE, "name": r.DENOM_SOCIAL, "fund_class_type": r.TP_FUNDO_CLASSE}
        for r in dims.itertuples()
    ]
    if rows:
        stmt = pg_insert(Fund).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["cnpj"],
            set_={"name": stmt.excluded.name, "fund_class_type": stmt.excluded.fund_class_type, "updated_at": datetime.utcnow()},
        )
        db.execute(stmt)
        db.flush()

    result = db.execute(select(Fund.cnpj, Fund.id).where(Fund.cnpj.in_(dims["CNPJ_FUNDO_CLASSE"].tolist())))
    return dict(result.all())


def _upsert_assets(db: Session, df: pd.DataFrame) -> dict[str, int]:
    dims = df[["CD_ATIVO", "DS_ATIVO", "CD_ISIN", "TP_ATIVO"]].drop_duplicates("CD_ATIVO")
    rows = [
        {
            "ticker": r.CD_ATIVO,
            "company_name": r.DS_ATIVO,
            "isin": r.CD_ISIN if pd.notna(r.CD_ISIN) else None,
            "asset_type": "bdr" if r.TP_ATIVO in BDR_TP_ATIVO else "equity",
        }
        for r in dims.itertuples()
    ]
    if rows:
        stmt = pg_insert(Asset).values(rows)
        stmt = stmt.on_conflict_do_update(
            index_elements=["ticker"],
            set_={"company_name": stmt.excluded.company_name, "isin": stmt.excluded.isin, "asset_type": stmt.excluded.asset_type},
        )
        db.execute(stmt)
        db.flush()

    result = db.execute(select(Asset.ticker, Asset.id).where(Asset.ticker.in_(dims["CD_ATIVO"].tolist())))
    return dict(result.all())


def _upsert_holdings(db: Session, df: pd.DataFrame, fund_ids: dict[str, int], asset_ids: dict[str, int], source_file: str) -> int:
    rows = [
        {
            "fund_id": fund_ids[r.CNPJ_FUNDO_CLASSE],
            "asset_id": asset_ids[r.CD_ATIVO],
            "ref_date": datetime.strptime(r.DT_COMPTC, "%Y-%m-%d").date(),
            "quantity": r.QT_POS_FINAL,
            "market_value": r.VL_MERC_POS_FINAL,
            "source_file": source_file,
            "ingested_at": datetime.utcnow(),
        }
        for r in df.itertuples()
    ]
    if not rows:
        return 0

    stmt = pg_insert(FundHolding).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fund_holdings_fund_asset_month",
        set_={
            "quantity": stmt.excluded.quantity,
            "market_value": stmt.excluded.market_value,
            "source_file": stmt.excluded.source_file,
            "ingested_at": stmt.excluded.ingested_at,
        },
    )
    db.execute(stmt)
    return len(rows)


def _upsert_nav(db: Session, df: pd.DataFrame, fund_ids: dict[str, int]) -> int:
    # PL occasionally lists the same fund twice in one month with identical
    # VL_PATRIM_LIQ but different TP_FUNDO_CLASSE ("FI" vs "CLASSES - FIF") —
    # a transition artifact of funds migrating to the Resolucao CVM 175
    # class structure (confirmed against real data, e.g. 202410). Keep one.
    df = df.drop_duplicates(subset=["CNPJ_FUNDO_CLASSE"], keep="first")
    rows = [
        {
            "fund_id": fund_ids[r.CNPJ_FUNDO_CLASSE],
            "ref_date": datetime.strptime(r.DT_COMPTC, "%Y-%m-%d").date(),
            "net_asset_value": r.VL_PATRIM_LIQ,
        }
        for r in df.itertuples()
        if r.CNPJ_FUNDO_CLASSE in fund_ids
    ]
    if not rows:
        return 0

    stmt = pg_insert(FundNav).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fund_nav_fund_month",
        set_={"net_asset_value": stmt.excluded.net_asset_value},
    )
    db.execute(stmt)
    return len(rows)


def ingest_month(db: Session, yyyymm: str, force_download: bool = False) -> int:
    """Ingest one competencia month end-to-end: equities + NAV. Returns rows processed.
    Idempotent — safe to call again for the same month (upsert on natural key)."""
    ref_date = yyyymm_to_ref_date_end_of_month(yyyymm)
    log = IngestionLog(source="cda", ref_date=ref_date, status="running")
    db.add(log)
    db.flush()

    try:
        zip_path = download_cda_zip(yyyymm, force=force_download)

        equities_df = parse_equities(zip_path)
        nav_df = parse_nav(zip_path)

        # NAV (PL file) covers every fund, including ones with zero equity exposure —
        # upsert funds from NAV first so the equities-only fund set below just adds to it.
        fund_ids = _upsert_funds(db, nav_df)
        fund_ids.update(_upsert_funds(db, equities_df))
        asset_ids = _upsert_assets(db, equities_df)

        holdings_rows = _upsert_holdings(db, equities_df, fund_ids, asset_ids, source_file=zip_path.name)
        nav_rows = _upsert_nav(db, nav_df, fund_ids)

        db.commit()

        log.status = "success"
        log.rows_processed = holdings_rows + nav_rows
        log.finished_at = datetime.utcnow()
        db.commit()
        logger.info("cda %s: ok — %d holdings, %d nav", yyyymm, holdings_rows, nav_rows)
        return holdings_rows + nav_rows
    except Exception as exc:  # noqa: BLE001 — logged into ingestion_log for a solo dev to notice
        db.rollback()
        log.status = "failed"
        log.error_message = str(exc)[:2000]
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        logger.exception("cda %s: falhou", yyyymm)
        raise
