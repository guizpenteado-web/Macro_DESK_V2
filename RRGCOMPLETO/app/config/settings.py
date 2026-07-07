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
    database_path: Path = ROOT_DIR / os.getenv("DATABASE_PATH", "database/rrg.db")
    log_path: Path = ROOT_DIR / os.getenv("LOG_PATH", "logs/")
    frontend_path: Path = ROOT_DIR / "frontend" / "index.html"

    # Download
    download_start_date: str = os.getenv("DOWNLOAD_START_DATE", "2023-01-01")
    download_max_workers: int = int(os.getenv("DOWNLOAD_MAX_WORKERS", "5"))

    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

    # Servidor
    port: int = int(os.getenv("PORT", "8021"))

    # Scheduler — roda 1x/dia depois do fechamento da B3
    scheduler_time: str = os.getenv("SCHEDULER_TIME", "19:00")

    # ── Metodologia RRG (ver plano — ajustar aqui, não espalhar no código) ──
    RS_RATIO_SMA_WEEKS: int = 10       # suavização da força relativa (RelPrice / SMA)
    RS_MOMENTUM_SMA_WEEKS: int = 3     # suavização do momentum (RS_Ratio / SMA(RS_Ratio))
    MAX_WEEKS: int = 52                # máximo de semanas retidas por ativo

    # Score de Rotação (0-100): 50 (neutro) + ajustes clamped + persistência
    SCORE_BASE: float = 50.0
    SCORE_RS_WEIGHT: float = 1.2
    SCORE_MOM_WEIGHT: float = 0.8
    SCORE_RS_CLAMP: float = 20.0
    SCORE_MOM_CLAMP: float = 20.0
    SCORE_PERSISTENCE_PER_WEEK: float = 1.5
    SCORE_PERSISTENCE_CAP_WEEKS: int = 12

    def __post_init__(self) -> None:
        self.log_path.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()
settings.__post_init__()
