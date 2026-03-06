from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SleepDetectionLog(Base):
    __tablename__ = "sleep_detection_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("sleep_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    window_index: Mapped[int] = mapped_column(Integer, nullable=False)
    start_second: Mapped[float] = mapped_column(Float, nullable=False)
    end_second: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(24), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    model_source: Mapped[str] = mapped_column(String(24), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
