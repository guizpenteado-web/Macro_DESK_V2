"""One-off historical backfill for Informe Diario (quota value / performance).

Usage:
    .venv\\Scripts\\python.exe scripts\\backfill_quota.py [start_year] [end_yyyymm]

Defaults to 2006 .. current month (~20 years, matching the "ultimos 20 anos"
performance ranking ask). 2000-2005 exist too but are skipped by default —
pass an earlier start_year explicitly if ever needed.
"""
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill_quota")

from app.database import SessionLocal
from app.services.cvm_client import INF_DIARIO_HIST_LAST_YEAR
from app.services.inf_diario_ingestion import ingest_month_recent, ingest_year_hist


def current_yyyymm() -> str:
    today = date.today()
    if today.month == 1:
        return f"{today.year - 1}12"
    return f"{today.year}{today.month - 1:02d}"


def main() -> None:
    start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2006
    end_yyyymm = sys.argv[2] if len(sys.argv) > 2 else current_yyyymm()
    end_year, end_month = int(end_yyyymm[:4]), int(end_yyyymm[4:6])

    ok, failed = [], []

    for year in range(start_year, min(INF_DIARIO_HIST_LAST_YEAR, end_year) + 1):
        db = SessionLocal()
        try:
            results = ingest_year_hist(db, str(year))
            logger.info("%d: %d meses ingeridos", year, len(results))
            ok.append(year)
        except Exception:
            logger.exception("%d: falhou, seguindo pro proximo ano", year)
            failed.append(year)
        finally:
            db.close()

    if end_year > INF_DIARIO_HIST_LAST_YEAR:
        recent_start_year = max(start_year, INF_DIARIO_HIST_LAST_YEAR + 1)
        for year in range(recent_start_year, end_year + 1):
            m_start = 1
            m_end = 12 if year < end_year else end_month
            for month in range(m_start, m_end + 1):
                yyyymm = f"{year}{month:02d}"
                db = SessionLocal()
                try:
                    n = ingest_month_recent(db, yyyymm)
                    ok.append(yyyymm)
                except Exception:
                    logger.exception("%s: falhou, seguindo pro proximo mes", yyyymm)
                    failed.append(yyyymm)
                finally:
                    db.close()

    logger.info("backfill_quota concluido — sucesso: %d, falhas: %d %s", len(ok), len(failed), failed)


if __name__ == "__main__":
    main()
