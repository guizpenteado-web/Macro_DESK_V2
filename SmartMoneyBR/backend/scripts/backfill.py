"""One-off historical backfill — NOT on the recurring APScheduler, run manually.

Usage:
    .venv\\Scripts\\python.exe scripts\\backfill.py [start_yyyymm] [end_yyyymm]

Defaults to settings.historical_backfill_start .. current month.
Ingests each month's CDA equities+NAV, then computes movements for it
immediately after (so each month's classification always has its prior
month's holdings already loaded).
"""
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill")

from app.config import settings
from app.database import SessionLocal
from app.services.cda_ingestion import ingest_month
from app.services.comparison_engine import compute_movements
from app.utils.dates import month_range, yyyymm_to_ref_date_end_of_month


def current_yyyymm() -> str:
    today = date.today()
    # last FULLY closed month — current month's CDA won't be published yet
    if today.month == 1:
        return f"{today.year - 1}12"
    return f"{today.year}{today.month - 1:02d}"


def main() -> None:
    start = sys.argv[1] if len(sys.argv) > 1 else settings.historical_backfill_start.replace("-", "")
    end = sys.argv[2] if len(sys.argv) > 2 else current_yyyymm()

    months = month_range(start, end)
    logger.info("backfill: %d meses (%s .. %s)", len(months), start, end)

    ok, failed = [], []
    for yyyymm in months:
        db = SessionLocal()
        try:
            rows = ingest_month(db, yyyymm)
            n_moves = compute_movements(db, yyyymm_to_ref_date_end_of_month(yyyymm))
            logger.info("%s: %d linhas ingeridas, %d movimentos", yyyymm, rows, n_moves)
            ok.append(yyyymm)
        except Exception:
            logger.exception("%s: falhou, seguindo pro proximo mes", yyyymm)
            failed.append(yyyymm)
        finally:
            db.close()

    logger.info("backfill concluido — sucesso: %d, falhas: %d %s", len(ok), len(failed), failed)


if __name__ == "__main__":
    main()
