"""One-off historical backfill for pre-2024-07 data — NOT on the recurring
APScheduler, run manually. Fills everything before settings.historical_backfill_start:

  - 2014-01 .. 2022-12: annual HIST bundles (ingest_year, one zip per year)
  - 2023-01 .. 2024-06: monthly zips (ingest_month, same as the regular
    backfill script) — CVM switched from yearly to monthly zips in 2023 but
    our regular backfill only starts at 2024-07, so this fills the gap.

Movements are computed immediately after each period, in ascending
chronological order, so classification always has the correct prior period
already loaded (mirrors scripts/backfill.py).

Usage:
    .venv\\Scripts\\python.exe scripts\\backfill_historical.py [start_year]

Defaults to 2014. Closed years never get revised by the CVM, so this is
safe to interrupt and resume — already-ingested years/months are skipped
unless force-downloaded, and upserts are idempotent either way.
"""
import calendar
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("backfill_historical")

from app.config import settings
from app.database import SessionLocal
from app.services.cda_ingestion import ingest_month, ingest_year
from app.services.comparison_engine import compute_movements
from app.utils.dates import month_range


def month_end(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def main() -> None:
    start_year = int(sys.argv[1]) if len(sys.argv) > 1 else 2014

    ok, failed = [], []

    # 1) Annual bundles: start_year .. 2022
    for year in range(start_year, 2023):
        db = SessionLocal()
        try:
            rows = ingest_year(db, year)
            logger.info("%d: %d linhas ingeridas", year, rows)
            for month in range(1, 13):
                n_moves = compute_movements(db, month_end(year, month))
                logger.info("%d-%02d: %d movimentos", year, month, n_moves)
            db.commit()
            ok.append(str(year))
        except Exception:
            logger.exception("%d: falhou, seguindo pro proximo ano", year)
            failed.append(str(year))
        finally:
            db.close()

    # 2) Monthly gap: 2023-01 .. month before settings.historical_backfill_start
    gap_end_yyyymm = f"{int(settings.historical_backfill_start[:4])}{int(settings.historical_backfill_start[5:7]) - 1:02d}"
    if gap_end_yyyymm >= "202301":
        for yyyymm in month_range("202301", gap_end_yyyymm):
            db = SessionLocal()
            try:
                rows = ingest_month(db, yyyymm)
                ref_date = date(int(yyyymm[:4]), int(yyyymm[4:6]), calendar.monthrange(int(yyyymm[:4]), int(yyyymm[4:6]))[1])
                n_moves = compute_movements(db, ref_date)
                db.commit()
                logger.info("%s: %d linhas ingeridas, %d movimentos", yyyymm, rows, n_moves)
                ok.append(yyyymm)
            except Exception:
                logger.exception("%s: falhou, seguindo pro proximo mes", yyyymm)
                failed.append(yyyymm)
            finally:
                db.close()

    logger.info("backfill historico concluido — sucesso: %d, falhas: %d %s", len(ok), len(failed), failed)


if __name__ == "__main__":
    main()
