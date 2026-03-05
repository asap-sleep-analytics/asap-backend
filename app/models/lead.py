from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


DeviceType = Literal["ios", "android", "both"]
LeadStatusType = Literal["pending", "confirmed"]


class WaitlistLeadCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=80)
    email: str = Field(
        ...,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Validación básica del formato de correo.",
    )
    device: DeviceType = Field(default="ios")
    source: str = Field(default="landing-page", max_length=80)


class WaitlistLeadRecord(WaitlistLeadCreate):
    lead_id: str
    status: LeadStatusType
    created_at: datetime
    confirmed_at: datetime | None = None


class WaitlistLeadResponse(BaseModel):
    ok: bool = True
    message: str
    lead: WaitlistLeadRecord
    confirmation_url_preview: str | None = None


class WaitlistLeadConfirmResponse(BaseModel):
    ok: bool = True
    message: str
    lead: WaitlistLeadRecord


class WaitlistLeadResendRequest(BaseModel):
    email: str = Field(
        ...,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Correo usado durante el registro en la lista de espera.",
    )


class WaitlistLeadResendResponse(BaseModel):
    ok: bool = True
    message: str
    lead: WaitlistLeadRecord | None = None
    confirmation_url_preview: str | None = None
