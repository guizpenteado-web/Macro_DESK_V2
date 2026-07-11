from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Fund(Base):
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    cnpj: Mapped[str] = mapped_column(String(18), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    fund_class_type: Mapped[str | None] = mapped_column(String(50))  # TP_FUNDO_CLASSE raw (CLASSES - FIF / FI / CLASSES - FIP)
    manager_name: Mapped[str | None] = mapped_column(String(255))  # deferred to a later phase (cadastro dataset)
    status: Mapped[str | None] = mapped_column(String(30))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
