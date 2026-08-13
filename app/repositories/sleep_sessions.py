from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import SleepSession, User


def get_user_sleep_session(db: Session, session_id: str, user: User) -> SleepSession | None:
    return db.scalar(
        select(SleepSession).where(SleepSession.id == session_id, SleepSession.user_id == user.id)
    )
