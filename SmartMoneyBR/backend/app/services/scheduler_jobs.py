"""APScheduler job definitions — cadence mirrors each CVM source's real
refresh cadence (see docs/DATA_SOURCES.md). No Celery/Redis: single-process
in-memory scheduler is enough for a solo-dev, scheduled-refresh workload."""
from __future__ import annotations

import logging
from datetime import date

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.database import SessionLocal
from app.services.alert_engine import generate_all_alerts
from app.services.buyback_ingestion import ingest_buybacks
from app.services.cda_ingestion import ingest_month
from app.services.comparison_engine import compute_movements
from app.services.insider_ingestion import ingest_vlmo_year
from app.services.security_ingestion import ingest_fca_year
from app.utils.dates import yyyymm_to_ref_date_end_of_month

logger = logging.getLogger(__name__)


def _current_and_prior_yyyymm(n_months_back: int) -> list[str]:
    today = date.today()
    months = []
    y, m = today.year, today.month
    for _ in range(n_months_back):
        m -= 1
        if m == 0:
            y -= 1
            m = 12
        months.append(f"{y}{m:02d}")
    return list(reversed(months))


def run_ingest_and_compute(yyyymm: str, force_download: bool = False) -> None:
    db = SessionLocal()
    try:
        ingest_month(db, yyyymm, force_download=force_download)
        compute_movements(db, yyyymm_to_ref_date_end_of_month(yyyymm))
        # Achado 31/jul/2026: fund_holdings so cresce por este job (ate ~1M
        # linhas/mes), mas o limiar padrao do autovacuum (10% das linhas) leva
        # tempo demais pra disparar num total de 8mi+, deixando as estatisticas
        # do planner desatualizadas por semanas — causou um plano catastrofico
        # (nested loop materializado, 72 milhoes de comparacoes descartadas)
        # na pagina Fundos. ANALYZE explicito aqui (~0.2-0.6s, roda dentro da
        # mesma transacao) garante estatisticas frescas logo apos a unica
        # rotina que de fato muda esses dados, sem depender do timing do
        # autovacuum.
        db.execute(text("ANALYZE fund_holdings"))
        db.execute(text("ANALYZE fund_quota"))
        db.commit()
    except Exception:
        logger.exception("job cda %s falhou", yyyymm)
    finally:
        db.close()


def job_cda_recent() -> None:
    """Re-ingest the rolling last-3-competencia-months window — CDA revises
    these daily as fund administrators submit late/corrected filings.
    force_download=True is essential here: download_cda_zip() caches the zip
    on disk and reuses it forever unless told otherwise, so without forcing a
    fresh download this job would run daily but always reprocess the exact
    same stale (often very incomplete) snapshot from whenever the month was
    first ingested — silently freezing recent months' holder/quantity data
    far below reality. Confirmed 11/jul/2026: months 202604-202606 had
    30-70% fewer holdings rows than fully-filed prior months, causing every
    asset's holder-count timeline to show a fake cliff in the last 3 months."""
    for yyyymm in _current_and_prior_yyyymm(3):
        run_ingest_and_compute(yyyymm, force_download=True)


def job_cda_backfill_weekly() -> None:
    """Sweep M-4 through M-12 for the slower weekly-cadence refresh and catch
    up any still-missing historical months."""
    for yyyymm in _current_and_prior_yyyymm(12)[:9]:  # months 4..12 back
        run_ingest_and_compute(yyyymm)


def job_recompra() -> None:
    """CVM republishes the buyback-programs file daily in place (not
    partitioned by month) — always force a fresh download."""
    db = SessionLocal()
    try:
        ingest_buybacks(db, force_download=True)
        generate_all_alerts(db)
    except Exception:
        logger.exception("job recompra falhou")
    finally:
        db.close()


def job_vlmo() -> None:
    """VLMO republica o zip do ano corrente conforme novas negociacoes de
    insider sao arquivadas — so o ano corrente precisa refresh diario, anos
    fechados ja estao completos no cache local."""
    db = SessionLocal()
    try:
        ingest_vlmo_year(db, date.today().year, force_download=True)
        generate_all_alerts(db)
    except Exception:
        logger.exception("job vlmo falhou")
    finally:
        db.close()


def job_fca() -> None:
    """FCA e atualizado semanalmente pela CVM (declarado no proprio portal
    de dados abertos) — so o ano corrente precisa refresh."""
    db = SessionLocal()
    try:
        ingest_fca_year(db, date.today().year, force_download=True)
    except Exception:
        logger.exception("job fca falhou")
    finally:
        db.close()


def start_scheduler(timezone: str) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=timezone)
    scheduler.add_job(
        job_cda_recent,
        "cron",
        day_of_week="tue-sat",
        hour=9,
        minute=0,
        id="cda_recent",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_cda_backfill_weekly,
        "cron",
        day_of_week="sun",
        hour=3,
        minute=0,
        id="cda_backfill_weekly",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_recompra,
        "cron",
        hour=9,
        minute=30,
        id="recompra",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_vlmo,
        "cron",
        hour=9,
        minute=45,
        id="vlmo",
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        job_fca,
        "cron",
        day_of_week="mon",
        hour=10,
        minute=0,
        id="fca",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        "scheduler iniciado — jobs: cda_recent (ter-sab 09:00), cda_backfill_weekly (dom 03:00), "
        "recompra (diario 09:30), vlmo (diario 09:45), fca (seg 10:00)"
    )
    return scheduler
