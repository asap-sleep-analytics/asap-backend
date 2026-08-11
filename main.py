from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST, Histogram, generate_latest
from sqlalchemy import text
from starlette.responses import Response

from app.api.routes.admin import router as admin_router
from app.api.routes.analyze import router as analyze_router
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.leads import router as leads_router
from app.api.routes.sleep import router as sleep_router
from app.api.routes.sleep_v3 import router as sleep_v3_router
from app.core.config import settings
from app.core.errors import register_error_handlers
from app.core.logging_ import RequestIDMiddleware, setup_logging
from app.db.init_db import init_db
from app.db.session import SessionLocal
from app.services.ml_service import SleepModel


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="Backend de A.S.A.P. para analítica de apnea del sueño y procesamiento de metadatos de audio.",
    lifespan=lifespan,
)

setup_logging()

allow_all_origins = "*" in settings.cors_allowed_origins

app.add_middleware(RequestIDMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=not allow_all_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)

app.include_router(analyze_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(leads_router)
app.include_router(sleep_router)
app.include_router(sleep_v3_router)


REQUEST_DURATION = Histogram(
    "asap_http_request_duration_seconds",
    "HTTP request duration in seconds",
    buckets=[0.01, 0.05, 0.1, 0.5, 1, 2.5, 5, 10],
)


@app.get("/health", tags=["health"])
def healthcheck() -> dict:
    db_ok = False
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            db_ok = True
    except Exception:
        db_ok = False

    ml_model = SleepModel()
    ml_ok = ml_model.is_trained

    return {
        "status": "ok" if db_ok else "degraded",
        "database": "connected" if db_ok else "disconnected",
        "ml_model": "loaded" if ml_ok else "not_found",
        "app_env": settings.app_env,
    }


@app.get("/metrics", tags=["monitoring"])
def metrics() -> Response:
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
