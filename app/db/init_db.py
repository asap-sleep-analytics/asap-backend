from app.core.config import settings
from app.db.base import Base
from app.db.models.lead import Lead  # noqa: F401
from app.db.models.sleep_session import SleepSession  # noqa: F401
from app.db.models.user import User  # noqa: F401
from app.db.session import engine


def init_db() -> None:
    if settings.auto_create_tables:
        Base.metadata.create_all(bind=engine)
