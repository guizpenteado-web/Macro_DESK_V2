from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class PortfolioItem(Base):
    """Ativos (acoes/BDRs) que um usuario do Hub quer acompanhar — pedido
    16/jul/2026. Diferente de FundFavorite: aqui cada usuario tem sua propria
    lista, isolada pelo username repassado no header X-Hub-Username (injetado
    pelo unified_server.py no proxy, a partir da sessao de login do Hub)."""

    __tablename__ = "portfolio_items"
    __table_args__ = (
        UniqueConstraint("owner_username", "asset_id", name="uq_portfolio_owner_asset"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_username: Mapped[str] = mapped_column(String(80), index=True)
    asset_id: Mapped[int] = mapped_column(Integer, ForeignKey("assets.id"))
    added_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
