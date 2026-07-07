"""
Scheduler diario usando a biblioteca schedule.
Executa o pipeline completo no horario configurado.
"""
import time
import schedule
from app.config.settings import settings
from app.utils.logger import logger


def run_pipeline() -> None:
    """Pipeline completo: componentes > precos > indicadores > dashboard > report."""
    logger.info("=== Pipeline automatico iniciado ===")
    from app.downloader.ibov_components import sync_components
    from app.downloader.price_downloader import update_prices
    from app.indicators.calculator import calculate_indicators
    from app.dashboard.html_generator import generate_dashboard
    from app.reports.excel_report import generate_report

    sync_components()
    update_prices()
    calculate_indicators()
    generate_dashboard()
    generate_report()
    logger.success("=== Pipeline automatico concluido ===")


def start_scheduler() -> None:
    """Inicia o loop de agendamento diario."""
    schedule.every().day.at(settings.scheduler_time).do(run_pipeline)
    logger.info(f"Scheduler ativo — execucao diaria as {settings.scheduler_time}")
    logger.info("Pressione Ctrl+C para parar.")
    while True:
        schedule.run_pending()
        time.sleep(60)