from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    isin: Mapped[str | None] = mapped_column(String(12))
    company_name: Mapped[str | None] = mapped_column(String(255))
    asset_type: Mapped[str] = mapped_column(String(20), default="equity")
