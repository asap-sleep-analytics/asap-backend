import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Lead, LeadStatus
from app.models.lead import DeviceType, WaitlistLeadCreate, WaitlistLeadRecord
from app.services.email import send_waitlist_confirmation_email


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _build_confirmation_url(token: str) -> str:
    separator = "&" if "?" in settings.lead_confirm_url_base else "?"
    return f"{settings.lead_confirm_url_base}{separator}token={token}"


def _to_record(lead: Lead) -> WaitlistLeadRecord:
    return WaitlistLeadRecord(
        lead_id=lead.id,
        name=lead.name,
        email=lead.email,
        device=cast(DeviceType, lead.device),
        source=lead.source,
        status=lead.status.value,
        created_at=lead.created_at,
        confirmed_at=lead.confirmed_at,
    )


def _issue_confirmation_token(lead: Lead) -> str:
    token = secrets.token_urlsafe(32)
    lead.confirmation_token_hash = _hash_token(token)
    lead.token_expires_at = datetime.now(UTC) + timedelta(hours=settings.lead_token_ttl_hours)
    return _build_confirmation_url(token)


def send_confirmation_email_background(name: str, email: str, confirmation_url: str) -> None:
    send_waitlist_confirmation_email(
        name=name,
        email=email,
        confirmation_url=confirmation_url,
    )


def smtp_is_configured() -> bool:
    return bool(settings.smtp_host and settings.smtp_password)


def create_waitlist_lead(
    db: Session,
    payload: WaitlistLeadCreate,
) -> tuple[WaitlistLeadRecord, str, str | None, bool]:
    email = payload.email.strip().lower()
    existing = db.scalar(select(Lead).where(Lead.email == email))

    if existing and existing.status == LeadStatus.confirmed:
        existing.name = payload.name
        existing.device = payload.device
        existing.source = payload.source
        db.commit()
        db.refresh(existing)
        return _to_record(existing), "Este correo ya está confirmado en la lista de espera.", None, False

    if existing:
        existing.name = payload.name
        existing.device = payload.device
        existing.source = payload.source
        existing.status = LeadStatus.pending
        existing.confirmed_at = None
        lead = existing
    else:
        lead = Lead(
            name=payload.name,
            email=email,
            device=payload.device,
            source=payload.source,
            status=LeadStatus.pending,
        )
        db.add(lead)

    confirmation_url = _issue_confirmation_token(lead)

    db.commit()
    db.refresh(lead)

    smtp_ok = smtp_is_configured()
    if smtp_ok:
        message = "Registro guardado. Revisa tu correo para completar la doble confirmación."
    else:
        message = "Registro guardado. SMTP no está configurado; usa confirmation_url_preview para confirmar en local."

    return _to_record(lead), message, confirmation_url, smtp_ok


def resend_waitlist_confirmation(
    db: Session,
    email: str,
) -> tuple[WaitlistLeadRecord | None, str, str | None, bool]:
    normalized_email = email.strip().lower()
    lead = db.scalar(select(Lead).where(Lead.email == normalized_email))

    if not lead:
        return (None, "Si este correo existe en la lista de espera, se envió una nueva confirmación.", None, False)

    if lead.status == LeadStatus.confirmed:
        return _to_record(lead), "Este correo ya está confirmado en la lista de espera.", None, False

    confirmation_url = _issue_confirmation_token(lead)
    db.commit()
    db.refresh(lead)

    smtp_ok = smtp_is_configured()
    if smtp_ok:
        message = "Confirmación reenviada. Revisa tu correo."
    else:
        message = "Confirmación reenviada. SMTP no está configurado; usa confirmation_url_preview para confirmar en local."

    return _to_record(lead), message, confirmation_url, smtp_ok


def confirm_waitlist_lead(db: Session, token: str) -> tuple[WaitlistLeadRecord, str]:
    token_hash = _hash_token(token)
    lead = db.scalar(select(Lead).where(Lead.confirmation_token_hash == token_hash))

    if not lead:
        raise ValueError("Token de confirmación inválido.")

    if lead.status == LeadStatus.confirmed:
        return _to_record(lead), "El correo ya estaba confirmado."

    now = datetime.now(UTC)
    expires_at = lead.token_expires_at
    if expires_at and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)

    if not expires_at or expires_at < now:
        raise ValueError("El token expiró. Solicita un nuevo correo de confirmación.")

    lead.status = LeadStatus.confirmed
    lead.confirmed_at = now
    lead.confirmation_token_hash = None
    lead.token_expires_at = None

    db.commit()
    db.refresh(lead)

    return _to_record(lead), "Correo confirmado correctamente. Bienvenido a la lista de espera de A.S.A.P."


def list_waitlist_leads(
    db: Session,
    limit: int = 20,
    cursor: str | None = None,
) -> tuple[list[WaitlistLeadRecord], str | None]:
    from app.models.pagination import decode_cursor_parts, encode_cursor_parts

    query = select(Lead)

    if cursor:
        created_iso, row_id = decode_cursor_parts(cursor)
        cursor_dt = datetime.fromisoformat(created_iso)
        query = query.where(
            (Lead.created_at < cursor_dt)
            | ((Lead.created_at == cursor_dt) & (Lead.id < row_id))
        )

    query = query.order_by(Lead.created_at.desc(), Lead.id.desc()).limit(limit + 1)
    rows = db.scalars(query).all()

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = encode_cursor_parts([last.created_at.isoformat(), last.id])

    return [_to_record(item) for item in items], next_cursor
