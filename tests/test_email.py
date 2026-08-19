import smtplib
from email.message import EmailMessage

import pytest

from app.core.config import settings
from app.services.email import (
    SMTP_PRESETS,
    _build_from_header,
    _smtp_connection_settings,
    _smtp_provider,
    send_waitlist_confirmation_email,
)


@pytest.fixture
def smtp_settings():
    fields = [
        "smtp_provider",
        "smtp_host",
        "smtp_port",
        "smtp_username",
        "smtp_password",
        "smtp_from_name",
        "smtp_from_email",
        "smtp_reply_to",
        "smtp_use_tls",
        "smtp_use_ssl",
        "smtp_timeout_seconds",
    ]
    original = [(f, getattr(settings, f)) for f in fields]
    yield
    for f, value in original:
        setattr(settings, f, value)


def test_smtp_provider_acepta_presets(smtp_settings) -> None:
    for provider in ["custom", *SMTP_PRESETS.keys()]:
        settings.smtp_provider = provider
        assert _smtp_provider() == provider


def test_smtp_provider_desconocido_cae_a_custom(smtp_settings, caplog) -> None:
    settings.smtp_provider = "hotmail"
    with caplog.at_level("WARNING"):
        assert _smtp_provider() == "custom"
    assert "SMTP_PROVIDER desconocido" in caplog.text


def test_smtp_no_host_levanta_valueerror(smtp_settings) -> None:
    settings.smtp_provider = "custom"
    settings.smtp_host = None
    with pytest.raises(ValueError, match="SMTP host no configurado."):
        _smtp_connection_settings()


def test_smtp_connection_usa_host_y_preset(smtp_settings) -> None:
    settings.smtp_provider = "resend"
    settings.smtp_host = None
    settings.smtp_port = None
    settings.smtp_username = None
    settings.smtp_use_tls = True
    settings.smtp_use_ssl = False

    host, port, username, use_tls, use_ssl = _smtp_connection_settings()
    assert host == "smtp.resend.com"
    assert port == 587
    assert username == "resend"
    assert use_tls is True
    assert use_ssl is False


def test_smtp_connection_usa_valores_explicitos(smtp_settings) -> None:
    settings.smtp_provider = "custom"
    settings.smtp_host = "smtp.ejemplo.com"
    settings.smtp_port = 465
    settings.smtp_username = "usuario"
    settings.smtp_use_ssl = True

    host, port, username, _, use_ssl = _smtp_connection_settings()
    assert host == "smtp.ejemplo.com"
    assert port == 465
    assert username == "usuario"
    assert use_ssl is True


def test_build_from_header_con_nombre(smtp_settings) -> None:
    settings.smtp_from_name = "A.S.A.P. Salud"
    settings.smtp_from_email = "no-reply@asap-health.app"
    assert _build_from_header() == "A.S.A.P. Salud <no-reply@asap-health.app>"


def test_build_from_header_sin_nombre(smtp_settings) -> None:
    settings.smtp_from_name = "   "
    settings.smtp_from_email = "no-reply@asap-health.app"
    assert _build_from_header() == "no-reply@asap-health.app"


def test_envio_sin_smtp_configurado_devuelve_false(smtp_settings) -> None:
    settings.smtp_provider = "custom"
    settings.smtp_host = None
    assert send_waitlist_confirmation_email("Ana", "ana@example.com", "https://link") is False


def test_envio_con_smtp_simulado_devuelve_true(smtp_settings, monkeypatch) -> None:
    settings.smtp_provider = "custom"
    settings.smtp_host = "smtp.ejemplo.com"
    settings.smtp_username = "user"
    settings.smtp_password = "pass"
    settings.smtp_use_tls = True
    settings.smtp_use_ssl = False

    sent: list[EmailMessage] = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            self.host = host
            self.port = port
            self.timeout = timeout

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            self.called_starttls = True

        def login(self, username, password):
            assert username == "user"
            assert password == "pass"

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)

    assert send_waitlist_confirmation_email("Ana", "ana@example.com", "https://link") is True
    assert len(sent) == 1
    message = sent[0]
    assert message["To"] == "ana@example.com"
    assert message["Subject"] == "Confirma tu registro en la lista de espera de A.S.A.P."
    assert "https://link" in message.get_body().get_content()
    assert "Confirmar mi correo" in message.get_body(preferencelist=("html",)).get_content()


def test_envio_con_ssl_simulado_usa_smtp_ssl(smtp_settings, monkeypatch) -> None:
    settings.smtp_provider = "custom"
    settings.smtp_host = "smtp.ejemplo.com"
    settings.smtp_use_ssl = True
    settings.smtp_use_tls = False
    settings.smtp_username = None

    used = []

    class FakeSMTPSSL:
        def __init__(self, host, port, timeout):
            used.append((host, port, timeout))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, message):
            pass

    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTPSSL)

    assert send_waitlist_confirmation_email("Ana", "ana@example.com", "https://link") is True
    assert used == [("smtp.ejemplo.com", 587, settings.smtp_timeout_seconds)]


def test_envio_con_excepcion_devuelve_false(smtp_settings, monkeypatch, caplog) -> None:
    settings.smtp_provider = "custom"
    settings.smtp_host = "smtp.ejemplo.com"
    settings.smtp_use_ssl = False
    settings.smtp_username = None

    class BrokenSMTP:
        def __init__(self, host, port, timeout):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def send_message(self, message):
            raise OSError("conexión caída")

    monkeypatch.setattr(smtplib, "SMTP", BrokenSMTP)

    with caplog.at_level("ERROR"):
        assert send_waitlist_confirmation_email("Ana", "ana@example.com", "https://link") is False
    assert "No se pudo enviar el correo" in caplog.text
