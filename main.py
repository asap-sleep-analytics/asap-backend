from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes.analyze import router as analyze_router
from app.api.routes.admin import router as admin_router
from app.api.routes.auth import router as auth_router
from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.leads import router as leads_router
from app.api.routes.sleep import router as sleep_router
from app.core.config import settings
from app.db.init_db import init_db


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

# CORS abierto para desarrollo local. Restringir orígenes en producción.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(analyze_router)
app.include_router(admin_router)
app.include_router(auth_router)
app.include_router(dashboard_router)
app.include_router(leads_router)
app.include_router(sleep_router)


@app.get("/health", tags=["health"])
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}
