"""
Configuração centralizada do Loguru.
Importar `logger` deste módulo em todos os outros módulos.
"""
import sys
from pathlib import Path

from loguru import logger

from app.config.settings import settings


def setup_logger() -> None:
    """Configura handlers de console e arquivo com rotação."""
    logger.remove()  # remove handler padrão do stderr

    # Console — colorido
    logger.add(
        sys.stdout,
        level=settings.log_level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<8}</level> | <cyan>{name}</cyan> — {message}",
        colorize=True,
    )

    # Arquivo — rotação diária, retenção 30 dias
    log_file: Path = settings.log_path / "ibov_breadth_{time:YYYY-MM-DD}.log"
    logger.add(
        str(log_file),
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {name}:{line} — {message}",
        rotation="00:00",
        retention="30 days",
        encoding="utf-8",
    )


setup_logger()

__all__ = ["logger"]
