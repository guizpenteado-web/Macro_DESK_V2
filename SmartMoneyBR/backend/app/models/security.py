from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompanySecurity(Base):
    """Mapeamento ticker -> CNPJ da companhia (FCA — Formulario Cadastral,
    secao Valores Mobiliarios). Recompra/VLMO da CVM so trazem CNPJ+razao
    social, nunca ticker — essa tabela e o que permite buscar "PRIO3" e achar
    o CNPJ certo pra cruzar com as outras tabelas. Verificado 10/jul/2026:
    RDOR3 -> CNPJ 06.047.087/0001-39, bate exato com o CNPJ ja usado em
    company_buybacks pra Rede D'Or."""

    __tablename__ = "company_securities"
    __table_args__ = (UniqueConstraint("cnpj_companhia", "ticker", name="uq_company_securities_cnpj_ticker"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj_companhia: Mapped[str] = mapped_column(String(20), index=True)
    company_name: Mapped[str] = mapped_column(String(255))
    ticker: Mapped[str] = mapped_column(String(20), index=True)  # Codigo_Negociacao
    valor_mobiliario: Mapped[str | None] = mapped_column(String(100))  # "Acoes Ordinarias" etc

    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
