"""FCA (Formulario Cadastral) ingestion — so a secao valor_mobiliario, que
mapeia ticker (Codigo_Negociacao) ao CNPJ da companhia. Diferente de VLMO,
aqui a chave natural (cnpj_companhia, ticker) e estavel entre anos — um
upsert simples por ano acumula a cobertura sem precisar de full-replace.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime

import pandas as pd
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import CompanySecurity, IngestionLog
from app.services.cvm_client import download_fca_zip, extract_member

logger = logging.getLogger(__name__)


def _parse(raw: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(raw), sep=";", encoding="latin-1")
    return df[df["Codigo_Negociacao"].notna() & df["CNPJ_Companhia"].notna()]


def ingest_fca_year(db: Session, year: int, force_download: bool = True) -> int:
    log = IngestionLog(source="fca", ref_date=datetime.utcnow().date(), status="running")
    db.add(log)
    db.flush()
    try:
        zip_path = download_fca_zip(year, force=force_download)
        raw = extract_member(zip_path, f"fca_cia_aberta_valor_mobiliario_{year}.csv")
        if raw is None:
            raise FileNotFoundError(f"fca_cia_aberta_valor_mobiliario_{year}.csv nao encontrado no zip")
        df = _parse(raw)

        rows = [
            {
                "cnpj_companhia": r.CNPJ_Companhia,
                "company_name": r.Nome_Empresarial,
                "ticker": r.Codigo_Negociacao,
                "valor_mobiliario": r.Valor_Mobiliario if pd.notna(r.Valor_Mobiliario) else None,
            }
            for r in df.itertuples()
        ]
        # dedupe dentro do proprio ano (mesmo ticker pode aparecer em
        # multiplas versoes/datas de referencia do formulario)
        seen = {}
        for r in rows:
            seen[(r["cnpj_companhia"], r["ticker"])] = r
        rows = list(seen.values())

        if rows:
            stmt = pg_insert(CompanySecurity).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_company_securities_cnpj_ticker",
                set_={"company_name": stmt.excluded.company_name, "valor_mobiliario": stmt.excluded.valor_mobiliario},
            )
            db.execute(stmt)

        db.commit()
        log.status = "success"
        log.rows_processed = len(rows)
        log.finished_at = datetime.utcnow()
        db.commit()
        logger.info("fca %d: %d tickers", year, len(rows))
        return len(rows)
    except Exception:
        db.rollback()
        log.status = "failed"
        log.finished_at = datetime.utcnow()
        db.add(log)
        db.commit()
        logger.exception("fca %d: falhou", year)
        raise
