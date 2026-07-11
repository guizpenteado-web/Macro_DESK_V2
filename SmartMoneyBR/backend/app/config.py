from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=Path(__file__).resolve().parents[1] / ".env")

    database_url: str
    cvm_base_url: str = "https://dados.cvm.gov.br/dados"
    backend_port: int = 8100
    schedule_tz: str = "America/Sao_Paulo"
    data_cache_dir: Path = Path("./data_cache")
    historical_backfill_start: str = "2023-01"
    log_level: str = "INFO"


settings = Settings()
