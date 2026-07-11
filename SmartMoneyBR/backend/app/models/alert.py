from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Alert(Base):
    """Eventos notaveis derivados dos dados ja ingeridos (recompra declarada,
    insider comprando, fundo reabrindo posicao zerada) — nao vem de nenhuma
    fonte externa, e gerado por app/services/alert_engine.py rodando sobre as
    tabelas que ja existem. `dedupe_key` e derivado dos dados de origem (nao
    do id interno de outra tabela, que pode mudar em reingestoes full-replace
    como InsiderTrade) para que reprocessar nunca duplique o mesmo alerta."""

    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_alerts_dedupe_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(40), index=True)  # "buyback_new" | "insider_buy" | "fund_reopened"
    severity: Mapped[str] = mapped_column(String(10), default="info")  # info | success | warning
    title: Mapped[str] = mapped_column(String(300))
    message: Mapped[str | None] = mapped_column(String(1000))

    entity_type: Mapped[str | None] = mapped_column(String(30))  # "fund" | "asset" | "company"
    entity_id: Mapped[int | None] = mapped_column()

    ref_date: Mapped[date] = mapped_column(Date, index=True)  # data do evento de origem
    dedupe_key: Mapped[str] = mapped_column(String(300))

    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
