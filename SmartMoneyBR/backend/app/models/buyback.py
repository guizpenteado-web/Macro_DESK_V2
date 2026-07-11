from datetime import date, datetime

from sqlalchemy import Date, DateTime, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class CompanyBuyback(Base):
    """Programa de Recompra de Acoes — CVM 'Eventos Societarios Especiais'
    (dados.cvm.gov.br/dataset/cia_aberta-eventos-recompra_acoes). Unlike
    CDA/Informe Diario this is a SINGLE small CSV with full history
    (~1.9k rows as of 2026-07), refreshed daily by the CVM — ingestion is a
    straight upsert of the whole file every run, keyed on the CVM's own
    ID_Programa (used directly as the primary key here)."""

    __tablename__ = "company_buybacks"

    id: Mapped[int] = mapped_column(primary_key=True)  # = ID_Programa da CVM
    cnpj: Mapped[str] = mapped_column(String(20), index=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    declared_at: Mapped[date] = mapped_column(Date, index=True)  # Data_Deliberacao
    deadline: Mapped[date | None] = mapped_column(Date)  # Data_Final_Prazo
    status: Mapped[str] = mapped_column(String(20))  # Situacao: "Em Andamento" | "Encerrado"
    operation_type: Mapped[str | None] = mapped_column(String(20))  # Tipo_Operacao: "Compra" | "Venda"
    reason: Mapped[str | None] = mapped_column(String(500))  # Motivo
    purpose: Mapped[str | None] = mapped_column(String(200))  # Finalidade_Compra
    qty_common_shares: Mapped[float | None] = mapped_column(Numeric(20, 2))  # Quantidade_Acoes_Ordinarias
    qty_preferred_shares: Mapped[float | None] = mapped_column(Numeric(20, 2))  # Quantidade_Acoes_Preferenciais

    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
