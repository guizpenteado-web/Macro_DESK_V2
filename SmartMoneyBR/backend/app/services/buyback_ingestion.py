"""Programa de Recompra de Acoes ingestion — a single always-current CSV
(not partitioned by month like CDA/Informe Diario), so every run is a
straight upsert of the whole file, keyed on the CVM's own ID_Programa.

Verified against the real file on 2026-07-10: 1914 rows, 1997-01-10 to
2026-07-02, columns ID_Programa;CNPJ_Companhia;Nome_Companhia;
Data_Deliberacao;Data_Final_Prazo;Situacao;Tipo_Operacao;Motivo;
Finalidade_Compra;Quantidade_Acoes_Ordinarias;Quantidade_Acoes_Preferenciais.
Separator ';', encoding latin-1 (same as every other CVM open-data CSV in
this project), dates as YYYY-MM-DD already (no parsing quirks found).
"""
from __future__ import annotations

import io
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import CompanyBuyback, IngestionLog
from app.services.cvm_client import download_recompra_zip, extract_member

logger = logging.getLogger(__name__)


def _parse(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="latin-1")
    df["Data_Deliberacao"] = pd.to_datetime(df["Data_Deliberacao"], errors="coerce").dt.date
    df["Data_Final_Prazo"] = pd.to_datetime(df["Data_Final_Prazo"], errors="coerce").dt.date
    return df


def ingest_buybacks(db: Session, force_download: bool = True) -> int:
    log = IngestionLog(source="recompra", ref_date=datetime.utcnow().date(), status="running")
    db.add(log)
    db.flush()
    try:
        zip_path = download_recompra_zip(force=force_download)
        raw = extract_member(zip_path, "cia_aberta_recompra_acoes.csv")
        if raw is None:
            raise FileNotFoundError("cia_aberta_recompra_acoes.csv nao encontrado no zip")
        df = _parse(raw)

        rows = [
            {
                "id": int(r.ID_Programa),
                "cnpj": r.CNPJ_Companhia,
                "company_name": r.Nome_Companhia,
                "declared_at": r.Data_Deliberacao,
                "deadline": r.Data_Final_Prazo,
                "status": r.Situacao,
                "operation_type": r.Tipo_Operacao if pd.notna(r.Tipo_Operacao) else None,
                "reason": r.Motivo if pd.notna(r.Motivo) else None,
                "purpose": r.Finalidade_Compra if pd.notna(r.Finalidade_Compra) else None,
                "qty_common_shares": float(r.Quantidade_Acoes_Ordinarias) if pd.notna(r.Quantidade_Acoes_Ordinarias) else None,
                "qty_preferred_shares": float(r.Quantidade_Acoes_Preferenciais)
                if pd.notna(r.Quantidade_Acoes_Preferenciais)
                else None,
            }
            for r in df.itertuples()
            if pd.notna(r.Data_Deliberacao)
        ]

        if rows:
            stmt = pg_insert(CompanyBuyback).values(rows)
            stmt = stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "cnpj": stmt.excluded.cnpj,
                    "company_name": stmt.excluded.company_name,
                    "declared_at": stmt.excluded.declared_at,
                    "deadline": stmt.excluded.deadline,
                    "status": stmt.excluded.status,
                    "operation_type": stmt.excluded.operation_type,
                    "reason": stmt.excluded.reason,
                    "purpose": stmt.excluded.purpose,
                    "qty_common_shares": stmt.excluded.qty_common_shares,
                    "qty_preferred_shares": stmt.excluded.qty_preferred_shares,
                },
            )
            db.execute(stmt)

        db.commit()
        log.status = "success"
        log.rows_processed = len(rows)
        log.finished_at = datetime.utcnow()
        db.commit()
        logger.info("recompra: %d programas", len(rows))
        return len(rows)
    except Exception:
        db.rollback()
        log.status = "failed"
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        logger.exception("recompra: falhou")
        raise
