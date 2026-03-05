import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SMTPPreset:
    host: str
    port: int
    username_hint: str | None


SMTP_PRESETS: dict[str, SMTPPreset] = {
    "resend": SMTPPreset(host="smtp.resend.com", port=587, username_hint="resend"),
    "sendgrid": SMTPPreset(host="smtp.sendgrid.net", port=587, username_hint="apikey"),
    "gmail": SMTPPreset(host="smtp.gmail.com", port=587, username_hint=None),
}


def _smtp_provider() -> str:
    provider = settings.smtp_provider.strip().lower()
    if provider in {"custom", *SMTP_PRESETS.keys()}:
        return provider

    logger.warning("SMTP_PROVIDER desconocido='%s'. Se usará custom.", settings.smtp_provider)
    return "custom"


def _smtp_connection_settings() -> tuple[str, int, str | None, bool, bool]:
    provider = _smtp_provider()
    preset = SMTP_PRESETS.get(provider)

    host = settings.smtp_host or (preset.host if preset else None)
    if not host:
        raise ValueError("SMTP host no configurado.")

    port = settings.smtp_port or (preset.port if preset else 587)
    username = settings.smtp_username or (preset.username_hint if preset else None)

    return host, port, username, settings.smtp_use_tls, settings.smtp_use_ssl


def _build_from_header() -> str:
    name = settings.smtp_from_name.strip()
    if not name:
        return settings.smtp_from_email
    return f"{name} <{settings.smtp_from_email}>"


def send_waitlist_confirmation_email(name: str, email: str, confirmation_url: str) -> bool:
    try:
        host, port, username, use_tls, use_ssl = _smtp_connection_settings()
    except ValueError:
        logger.info("SMTP no configurado. Usa confirmation_url_preview durante desarrollo local.")
        return False

    message = EmailMessage()
    message["Subject"] = "Confirma tu registro en la lista de espera de A.S.A.P."
    message["From"] = _build_from_header()
    message["To"] = email
    if settings.smtp_reply_to:
        message["Reply-To"] = settings.smtp_reply_to

    message.set_content(
        (
            f"Hola {name},\n\n"
            "Confirma tu correo para unirte a la lista de espera de A.S.A.P.\n"
            f"Enlace de confirmación: {confirmation_url}\n\n"
            "Si no solicitaste este registro, puedes ignorar este mensaje."
        )
    )
    message.add_alternative(
        (
            "<html><body>"
            f"<p>Hola {name},</p>"
            "<p>Confirma tu correo para unirte a la lista de espera de A.S.A.P.</p>"
            f"<p><a href=\"{confirmation_url}\">Confirmar mi correo</a></p>"
            "<p>Si no solicitaste este registro, puedes ignorar este mensaje.</p>"
            "</body></html>"
        ),
        subtype="html",
    )

    try:
        smtp_client = smtplib.SMTP_SSL if use_ssl else smtplib.SMTP
        with smtp_client(host, port, timeout=settings.smtp_timeout_seconds) as smtp:
            if use_tls and not use_ssl:
                smtp.starttls()

            if username and settings.smtp_password:
                smtp.login(username, settings.smtp_password)

            smtp.send_message(message)
        return True
    except Exception as exc:  # pragma: no cover - depends on external SMTP server
        logger.exception("No se pudo enviar el correo de confirmación: %s", exc)
        return False
