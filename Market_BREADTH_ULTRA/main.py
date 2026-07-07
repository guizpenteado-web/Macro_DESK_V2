"""
IBOV Market Breadth — Entry Point

Modos:
    python main.py run        — pipeline completo (padrao)
    python main.py schedule   — scheduler automatico diario
    python main.py dashboard  — so gera o dashboard
    python main.py report     — so gera o Excel
"""
import sys
import time


def main() -> None:
    from app.utils.logger import logger
    from app.database.connection import init_database

    mode = sys.argv[1] if len(sys.argv) > 1 else "run"
    logger.info(f"IBOV Market Breadth | modo: {mode}")
    init_database()

    if   mode == "run":      _pipeline()
    elif mode == "schedule":  _schedule()
    elif mode == "dashboard": _dashboard()
    elif mode == "report":    _report()
    else:
        logger.error(f"Modo desconhecido: {mode}")
        sys.exit(1)


def _pipeline() -> None:
    from app.utils.logger import logger
    from app.downloader.ibov_components import sync_components
    from app.downloader.price_downloader import update_prices
    from app.indicators.calculator import calculate_indicators
    from app.dashboard.html_generator import generate_dashboard
    from app.reports.excel_report import generate_report
    from app.utils.helpers import open_in_browser
    from app.config.settings import settings

    t0 = time.time()
    logger.info("Etapa 1/5 — Sincronizando componentes do IBOVESPA...")
    n_assets = sync_components()

    logger.info("Etapa 2/5 — Baixando precos...")
    update_prices()

    logger.info("Etapa 3/5 — Calculando indicadores e breadth...")
    calculate_indicators()

    logger.info("Etapa 4/5 — Gerando dashboard...")
    dash = generate_dashboard()

    logger.info("Etapa 5/5 — Gerando relatorio Excel...")
    generate_report()

    elapsed = time.time() - t0
    logger.success(f"Pipeline concluido em {elapsed:.1f}s | {n_assets} ativos")
    logger.info(f"Dashboard: {dash}")
    logger.info(f"Relatorio: {settings.reports_output / "ibov_breadth_report.xlsx"}")
    open_in_browser(dash)


def _schedule() -> None:
    from app.scheduler.tasks import run_pipeline, start_scheduler
    run_pipeline()
    start_scheduler()


def _dashboard() -> None:
    from app.dashboard.html_generator import generate_dashboard
    from app.utils.helpers import open_in_browser
    dash = generate_dashboard()
    open_in_browser(dash)


def _report() -> None:
    from app.reports.excel_report import generate_report
    generate_report()


if __name__ == "__main__":
    main()