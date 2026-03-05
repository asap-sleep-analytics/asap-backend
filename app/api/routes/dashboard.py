from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.models.dashboard import DashboardResumenResponse
from app.services.dashboard import get_dashboard_summary

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/resumen", response_model=DashboardResumenResponse)
def dashboard_summary_endpoint(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DashboardResumenResponse:
    return get_dashboard_summary(db=db, current_user=current_user)
