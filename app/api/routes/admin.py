from typing import Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.services.admin import build_dataset_export_csv, build_dataset_export_rows

router = APIRouter(prefix="/api/admin", tags=["admin"])


def _validate_admin_export_key(header_value: str | None) -> None:
    if not header_value or header_value != settings.admin_dataset_export_key:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Acceso de exportación no autorizado.")


@router.get("/dataset/export")
def export_dataset_endpoint(
    format: Literal["json", "csv"] = Query(default="json"),
    limit: int = Query(default=10000, ge=1, le=50000),
    x_admin_export_key: str | None = Header(default=None, alias="X-Admin-Export-Key"),
    db: Session = Depends(get_db),
):
    _validate_admin_export_key(x_admin_export_key)

    rows = build_dataset_export_rows(db=db, limit=limit)

    if format == "csv":
        payload = build_dataset_export_csv(rows)
        return Response(
            content=payload,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=asap_dataset_export.csv"},
        )

    return {
        "ok": True,
        "mensaje": "Exportación generada correctamente.",
        "rows": rows,
        "total": len(rows),
    }
