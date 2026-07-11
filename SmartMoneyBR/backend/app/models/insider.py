from datetime import date, datetime

from sqlalchemy import Date, DateTime, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class InsiderTrade(Base):
    """Valores Mobiliarios Negociados e Detidos (VLMO) — CVM, negociacao de
    administradores/conselheiros/controladores com valores mobiliarios da
    propria companhia (Resolucao CVM 44). NAO tem nome do individuo nos
    dados abertos — so o cargo agregado (Tipo_Cargo). Verificado 10/jul/2026:
    schema sem chave natural de linha, entao cada reingestao de um ano faz
    full-replace (DELETE+INSERT) das linhas daquele source_year, em vez de
    upsert por chave composta."""

    __tablename__ = "insider_trades"
    __table_args__ = (
        Index("ix_insider_trades_cnpj_date", "cnpj_companhia", "data_movimentacao"),
        Index("ix_insider_trades_source_year", "source_year"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    source_year: Mapped[int] = mapped_column(Integer)  # ano do arquivo CVM (vlmo_cia_aberta_con_{year}.csv)

    cnpj_companhia: Mapped[str] = mapped_column(String(20), index=True)
    company_name: Mapped[str] = mapped_column(String(255), index=True)
    data_referencia: Mapped[date] = mapped_column(Date)
    versao: Mapped[int | None] = mapped_column(Integer)

    tipo_empresa: Mapped[str | None] = mapped_column(String(20))  # Companhia | Controladora | Controlada
    empresa: Mapped[str | None] = mapped_column(String(255))  # qual entidade do grupo negociou
    tipo_cargo: Mapped[str | None] = mapped_column(String(60))  # Conselho/Diretor/Controlador/Fiscal/Estatutario

    tipo_movimentacao: Mapped[str] = mapped_column(String(80))  # "Compra a vista", "Saldo Inicial" etc — valor cru da CVM
    direction: Mapped[str | None] = mapped_column(String(10))  # "COMPRA" | "VENDA" | None (classificado na ingestao)
    tipo_operacao: Mapped[str | None] = mapped_column(String(10))  # Credito | Debito
    tipo_ativo: Mapped[str | None] = mapped_column(String(80))  # Acoes, Opcao de Compra, Debentures...
    caracteristica_valor_mobiliario: Mapped[str | None] = mapped_column(String(60))
    intermediario: Mapped[str | None] = mapped_column(String(200))

    data_movimentacao: Mapped[date | None] = mapped_column(Date)  # null para "Saldo Inicial"
    quantidade: Mapped[float | None] = mapped_column(Numeric(20, 4))
    preco_unitario: Mapped[float | None] = mapped_column(Numeric(20, 10))
    volume: Mapped[float | None] = mapped_column(Numeric(20, 2))

    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
