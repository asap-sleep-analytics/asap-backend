from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit_dependency
from app.core.security import get_current_user
from app.db.models import User
from app.db.session import get_db
from app.models.lead import (
    WaitlistLeadConfirmResponse,
    WaitlistLeadCreate,
    WaitlistLeadResendRequest,
    WaitlistLeadResendResponse,
    WaitlistLeadResponse,
)
from app.services.leads import (
    confirm_waitlist_lead,
    create_waitlist_lead,
    list_waitlist_leads,
    resend_waitlist_confirmation,
    send_confirmation_email_background,
)

router = APIRouter(prefix="/api/v1", tags=["waitlist"])


@router.post("/leads", response_model=WaitlistLeadResponse, status_code=status.HTTP_201_CREATED)
def create_waitlist_lead_endpoint(
    lead: Annotated[WaitlistLeadCreate, Body()],
    background_tasks: BackgroundTasks,
    _: None = Depends(rate_limit_dependency(max_requests=5, window_seconds=60)),
    db: Session = Depends(get_db),
) -> WaitlistLeadResponse:
    created, message, confirmation_url, smtp_ok = create_waitlist_lead(db=db, payload=lead)
    if smtp_ok and confirmation_url is not None:
        background_tasks.add_task(
            send_confirmation_email_background,
            name=created.name,
            email=created.email,
            confirmation_url=confirmation_url,
        )
    return WaitlistLeadResponse(
        message=message,
        lead=created,
        confirmation_url_preview=None if smtp_ok else confirmation_url,
    )


@router.get("/leads")
def get_waitlist_leads(
    limit: int = Query(default=20, ge=1, le=200),
    cursor: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    try:
        items, next_cursor = list_waitlist_leads(db=db, limit=limit, cursor=cursor)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return {"items": items, "next_cursor": next_cursor, "has_more": next_cursor is not None}


@router.get("/leads/confirm", response_model=WaitlistLeadConfirmResponse)
def confirm_waitlist_lead_endpoint(
    token: str = Query(..., min_length=20),
    db: Session = Depends(get_db),
) -> WaitlistLeadConfirmResponse:
    try:
        lead, message = confirm_waitlist_lead(db=db, token=token)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return WaitlistLeadConfirmResponse(message=message, lead=lead)


@router.post("/leads/resend-confirmation", response_model=WaitlistLeadResendResponse)
def resend_waitlist_confirmation_endpoint(
    payload: Annotated[WaitlistLeadResendRequest, Body()],
    background_tasks: BackgroundTasks,
    _: None = Depends(rate_limit_dependency(max_requests=3, window_seconds=120)),
    db: Session = Depends(get_db),
) -> WaitlistLeadResendResponse:
    lead, message, confirmation_url, smtp_ok = resend_waitlist_confirmation(db=db, email=payload.email)
    if smtp_ok and lead is not None and confirmation_url is not None:
        background_tasks.add_task(
            send_confirmation_email_background,
            name=lead.name,
            email=lead.email,
            confirmation_url=confirmation_url,
        )
    return WaitlistLeadResendResponse(
        message=message,
        lead=lead,
        confirmation_url_preview=None if smtp_ok else confirmation_url,
    )
