from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class FundFavorite(Base):
    """Fundos marcados como favoritos por um admin do Hub — pedido do usuario
    15/jul/2026. Lista compartilhada (sem conceito de usuario dentro do
    proprio Postgres do SmartMoneyBR); favoritar/desfavoritar sao POST/DELETE,
    ja bloqueados pra quem nao e' admin pelo middleware central do Hub
    (unified_server.py), entao nao precisa reimplementar checagem de role
    aqui — so' GET (leitura) e' publico, igual o resto do app."""

    __tablename__ = "fund_favorites"

    fund_id: Mapped[int] = mapped_column(Integer, ForeignKey("funds.id"), primary_key=True)
    favorited_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
