import os
from collections.abc import Generator
from pathlib import Path

os.environ.setdefault("DISABLE_RATE_LIMIT", "1")

# Tests deterministas: no cargar el modelo v3 real (grande e incompatible en CI).
os.environ.setdefault("ML_V3_MODEL_DIR", os.path.join(os.getcwd(), "tests", "_empty_models"))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.core.rate_limit import reset_rate_limiter_for_tests  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import get_db  # noqa: E402
from main import app  # noqa: E402


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "postgresql: mark test to run only when TEST_DATABASE_URL points to PostgreSQL",
    )


def _build_test_engine(tmp_path: Path):
    test_url = os.getenv("TEST_DATABASE_URL")
    if test_url:
        engine = create_engine(test_url, pool_pre_ping=True)
        return engine, test_url

    test_db_file = tmp_path / "asap_test.db"
    test_database_url = f"sqlite:///{test_db_file}"
    engine = create_engine(test_database_url, connect_args={"check_same_thread": False})
    return engine, test_database_url


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> Generator[None]:
    reset_rate_limiter_for_tests()
    yield


@pytest.fixture()
def client(tmp_path: Path) -> Generator[TestClient]:
    engine, _ = _build_test_engine(tmp_path)
    testing_session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.state.test_engine = engine
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    app.state.test_engine = None
    engine.dispose()
