"""
Configurações centrais da aplicação.
Carrega variáveis do .env e expõe um objeto Settings singleton.
"""
from pathlib import Path
from dotenv import load_dotenv
import os

# Raiz do projeto (dois níveis acima deste arquivo)
ROOT_DIR = Path(__file__).resolve().parents[2]

load_dotenv(ROOT_DIR / ".env")


class Settings:
    """Configurações carregadas do ambiente ou valores padrão."""

    # Paths
    root_dir: Path = ROOT_DIR
    database_path: Path = ROOT_DIR / os.getenv("DATABASE_PATH", "database/ibov_breadth.db")
    log_path: Path = ROOT_DIR / os.getenv("LOG_PATH", "logs/")
    dashboard_output: Path = ROOT_DIR / os.getenv("DASHBOARD_OUTPUT", "dashboard/index.html")
    reports_output: Path = ROOT_DIR / os.getenv("REPORTS_OUTPUT", "reports/")

    # Download
    download_start_date: str = os.getenv("DOWNLOAD_START_DATE", "2017-01-01")
    download_max_workers: int = int(os.getenv("DOWNLOAD_MAX_WORKERS", "5"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Scheduler
    scheduler_time: str = os.getenv("SCHEDULER_TIME", "18:30")

    # Indicadores
    sma_periods: list[int] = [21, 50, 200]

    def __post_init__(self) -> None:
        """Garante que os diretórios necessários existem."""
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.reports_output.mkdir(parents=True, exist_ok=True)
        self.dashboard_output.parent.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


# Singleton — importe de qualquer módulo
settings = Settings()
