from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(12))
    company_name: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(20), default="equity")
    # Soft-hide (16/jul/2026, pedido do usuario): ativo sem giro relevante
    # em bolsa (media <R$100mil/dia nos ultimos 180 pregoes, ou sem nenhum
    # pregao no periodo). NAO e' hard delete -- fund_holdings/portfolio_items
    # tem FK NO ACTION pra assets.id, um DELETE quebraria posicao historica
    # real de fundo. is_active=False so tira o ativo das telas (busca,
    # rankings, listagem) sem apagar historico nenhum.
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
