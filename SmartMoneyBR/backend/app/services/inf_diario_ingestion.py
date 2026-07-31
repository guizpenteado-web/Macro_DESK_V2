"""Informe Diario ingestion — monthly quota-value snapshots (last trading day
of the month), covering 2000-present via two coexisting CVM locations:
- HIST/ (2000-2020): one zip per YEAR, containing 12 monthly CSVs inside
- DADOS/ (2021-present): one zip per MONTH

See docs/DATA_SOURCES.md for verified column-naming eras:
- 2000-2020ish:  CNPJ_FUNDO;DT_COMPTC;VL_TOTAL;VL_QUOTA;VL_PATRIM_LIQ;CAPTC_DIA;RESG_DIA;NR_COTST
- 2021-2024ish:  TP_FUNDO;CNPJ_FUNDO;...(same tail)
- Oct/2024+:     TP_FUNDO_CLASSE;CNPJ_FUNDO_CLASSE;ID_SUBCLASSE;...(same tail)

Only the fund-key and quota columns are used here; TP_FUNDO(_CLASSE) is not
needed for this ingestion (funds are already keyed by CNPJ everywhere else).
We ingest one row per fund per MONTH (last available trading day), not full
daily granularity — sufficient for return/performance ranking, ~22x less
volume than true daily ingestion across 20+ years of history.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import Fund, FundQuota, IngestionLog
from app.services.cvm_client import (
    download_inf_diario_month,
    download_inf_diario_year,
    extract_member,
)
from app.utils.dates import yyyymm_to_ref_date_end_of_month

logger = logging.getLogger(__name__)

# Both possible spellings for the fund-key column across eras.
CNPJ_COL_CANDIDATES = ("CNPJ_FUNDO_CLASSE", "CNPJ_FUNDO")


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if "CNPJ_FUNDO" in df.columns and "CNPJ_FUNDO_CLASSE" not in df.columns:
        df = df.rename(columns={"CNPJ_FUNDO": "CNPJ_FUNDO_CLASSE"})
    return df


def _last_trading_day_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Reduce a month's daily rows to one row per fund — its last available
    trading day that month (handles funds that stop trading mid-month too).

    Real bug found 31/jul/2026: alguns administradores reportam tardiamente
    pra CVM nos ultimos dias do mes, e o arquivo publicado traz uma linha
    "vazia" (VL_QUOTA=0 E VL_PATRIM_LIQ=0 E NR_COTST=0) nesses dias em vez de
    simplesmente omitir o fundo. VL_QUOTA=0 e matematicamente impossivel pra
    um fundo em operacao normal (confirmado: ~250 fundos caiam de patrimonio
    real, ex. R$10M/4 cotistas, pra exatamente zero nos ultimos 1-2 pregoes
    do mes, sem nenhuma transicao gradual — assinatura de dado nao reportado,
    nao de fundo real fechando). Filtramos essas linhas degeneradas ANTES de
    pegar o ultimo dia, senao a snapshot do mes inteiro fica zerada quando o
    dado real (das semanas anteriores, no mesmo arquivo) existe.
    """
    real = df[~((df["VL_PATRIM_LIQ"] == 0) & (df["NR_COTST"] == 0))]
    real = real.sort_values("DT_COMPTC")
    return real.groupby("CNPJ_FUNDO_CLASSE", as_index=False).last()


def _parse_month_csv(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(
        io.BytesIO(raw),
        sep=";",
        encoding="latin-1",
        low_memory=False,
        usecols=lambda c: c in {*CNPJ_COL_CANDIDATES, "DT_COMPTC", "VL_QUOTA", "VL_PATRIM_LIQ", "NR_COTST"},
    )
    df = _normalize_columns(df)
    return _last_trading_day_snapshot(df)


def _upsert_quotas(db: Session, df: pd.DataFrame, ref_date, source_file: str) -> int:
    if df.empty:
        return 0

    cnpjs = df["CNPJ_FUNDO_CLASSE"].dropna().unique().tolist()
    dims = df[["CNPJ_FUNDO_CLASSE"]].drop_duplicates()
    fund_rows = [{"cnpj": c, "name": c} for c in dims["CNPJ_FUNDO_CLASSE"]]
    # Informe Diario covers many funds never seen in CDA (fixed-income, etc.) —
    # upsert with DO NOTHING on name so we don't clobber a real name already
    # set by CDA ingestion with a placeholder equal to the CNPJ.
    stmt = pg_insert(Fund).values(fund_rows).on_conflict_do_nothing(index_elements=["cnpj"])
    db.execute(stmt)
    db.flush()

    fund_ids = dict(db.execute(select(Fund.cnpj, Fund.id).where(Fund.cnpj.in_(cnpjs))).all())

    rows = [
        {
            "fund_id": fund_ids[r.CNPJ_FUNDO_CLASSE],
            "ref_date": ref_date,
            "quota_value": r.VL_QUOTA,
            "net_asset_value": r.VL_PATRIM_LIQ,
            "n_shareholders": int(r.NR_COTST) if pd.notna(r.NR_COTST) else None,
        }
        for r in df.itertuples()
        if r.CNPJ_FUNDO_CLASSE in fund_ids and pd.notna(r.VL_QUOTA)
    ]
    if not rows:
        return 0

    stmt = pg_insert(FundQuota).values(rows)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_fund_quota_fund_month",
        set_={
            "quota_value": stmt.excluded.quota_value,
            "net_asset_value": stmt.excluded.net_asset_value,
            "n_shareholders": stmt.excluded.n_shareholders,
        },
    )
    db.execute(stmt)
    return len(rows)


def ingest_month_quota(db: Session, yyyymm: str, csv_bytes: bytes, source_file: str) -> int:
    ref_date = yyyymm_to_ref_date_end_of_month(yyyymm)
    log = IngestionLog(source="inf_diario", ref_date=ref_date, status="running")
    db.add(log)
    db.flush()
    try:
        df = _parse_month_csv(csv_bytes)
        n = _upsert_quotas(db, df, ref_date, source_file)
        db.commit()
        log.status = "success"
        log.rows_processed = n
        log.finished_at = datetime.utcnow()
        db.commit()
        return n
    except Exception:
        db.rollback()
        log.status = "failed"
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        logger.exception("inf_diario %s: falhou", yyyymm)
        raise


def ingest_year_hist(db: Session, yyyy: str, force_download: bool = False) -> dict[str, int]:
    """Ingest all 12 months contained in one HIST annual zip (2000-2020)."""
    zip_path = download_inf_diario_year(yyyy, force=force_download)
    results = {}
    for month in range(1, 13):
        yyyymm = f"{yyyy}{month:02d}"
        raw = extract_member(zip_path, f"inf_diario_fi_{yyyymm}.csv")
        if raw is None:
            continue
        n = ingest_month_quota(db, yyyymm, raw, source_file=zip_path.name)
        results[yyyymm] = n
        logger.info("inf_diario %s: %d fundos", yyyymm, n)
    return results


def ingest_month_recent(db: Session, yyyymm: str, force_download: bool = False) -> int:
    """Ingest one DADOS/ monthly zip (2021-present)."""
    zip_path = download_inf_diario_month(yyyymm, force=force_download)
    raw = extract_member(zip_path, f"inf_diario_fi_{yyyymm}.csv")
    if raw is None:
        raise FileNotFoundError(f"CSV nao encontrado em {zip_path}")
    n = ingest_month_quota(db, yyyymm, raw, source_file=zip_path.name)
    logger.info("inf_diario %s: %d fundos", yyyymm, n)
    return n
