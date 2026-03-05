from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.lead import (
    WaitlistLeadConfirmResponse,
    WaitlistLeadCreate,
    WaitlistLeadRecord,
    WaitlistLeadResendRequest,
    WaitlistLeadResendResponse,
    WaitlistLeadResponse,
)
from app.services.leads import (
    confirm_waitlist_lead,
    create_waitlist_lead,
    list_waitlist_leads,
    resend_waitlist_confirmation,
)

router = APIRouter(prefix="/api", tags=["waitlist"])


@router.post("/leads", response_model=WaitlistLeadResponse, status_code=status.HTTP_201_CREATED)
def create_waitlist_lead_endpoint(
    lead: WaitlistLeadCreate,
    db: Session = Depends(get_db),
) -> WaitlistLeadResponse:
    created, message, preview_url = create_waitlist_lead(db=db, payload=lead)
    return WaitlistLeadResponse(
        message=message,
        lead=created,
        confirmation_url_preview=preview_url,
    )


@router.get("/leads", response_model=list[WaitlistLeadRecord])
def get_waitlist_leads(
    limit: int = Query(default=20, ge=1, le=200),
    db: Session = Depends(get_db),
) -> list[WaitlistLeadRecord]:
    return list_waitlist_leads(db=db, limit=limit)


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
    payload: WaitlistLeadResendRequest,
    db: Session = Depends(get_db),
) -> WaitlistLeadResendResponse:
    lead, message, preview_url = resend_waitlist_confirmation(db=db, email=payload.email)
    return WaitlistLeadResendResponse(
        message=message,
        lead=lead,
        confirmation_url_preview=preview_url,
    )
