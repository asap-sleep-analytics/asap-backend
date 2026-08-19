import base64
import binascii
import json

from pydantic import BaseModel


class CursorPage(BaseModel):
    items: list
    next_cursor: str | None
    has_more: bool


def _decode_raw(cursor: str) -> str:
    """Decodifica un cursor base64 urlsafe y lo devuelve como texto.

    Levanta ``ValueError`` si el cursor no es base64 urlsafe válido o no
    contiene texto decodificable, para que la ruta responda 400 en vez de 500.
    """
    try:
        decoded = base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Cursor de paginación inválido.") from exc
    if not decoded:
        raise ValueError("Cursor de paginación inválido.")
    return decoded


def encode_cursor(value: str) -> str:
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(value: str) -> str:
    """Decodifica un cursor de paginación simple (un único valor)."""
    return _decode_raw(value)


def encode_cursor_parts(parts: list[str]) -> str:
    """Codifica un cursor compuesto (ej. fecha + id) de forma determinista.

    Usar un cursor compuesto con la clave primaria evita saltar o duplicar
    filas cuando el campo ordenado tiene valores repetidos.
    """
    payload = json.dumps(parts, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode()).decode()


def decode_cursor_parts(cursor: str) -> list[str]:
    """Decodifica un cursor compuesto. Levanta ``ValueError`` si es inválido."""
    decoded = _decode_raw(cursor)
    try:
        parts = json.loads(decoded)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("Cursor de paginación inválido.") from exc
    if not isinstance(parts, list) or not parts or not all(isinstance(p, str) and p for p in parts):
        raise ValueError("Cursor de paginación inválido.")
    return parts
