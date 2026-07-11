from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IngestionLog(Base):
    """Audit trail of every ingestion run — the only monitoring surface a solo
    dev has without Celery/external observability. Lets us notice a silently
    failed scheduled job."""

    __tablename__ = "ingestion_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(50))  # e.g. "cda"
    ref_date: Mapped[date] = mapped_column(Date)
    rows_processed: Mapped[int | None] = mapped_column()
    started_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="running")  # running | success | failed
    error_message: Mapped[str | None] = mapped_column(Text)
