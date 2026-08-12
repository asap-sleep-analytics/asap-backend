from pydantic import BaseModel


class CursorPage(BaseModel):
    items: list
    next_cursor: str | None
    has_more: bool


def encode_cursor(value: str) -> str:
    import base64
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(value: str) -> str:
    """Decodifica un cursor de paginación.

    Levanta ``ValueError`` si el cursor no es base64 urlsafe válido o no
    contiene texto decodificable, para que la ruta responda 400 en vez de 500.
    """
    import base64
    import binascii

    try:
        decoded = base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError("Cursor de paginación inválido.") from exc
    if not decoded:
        raise ValueError("Cursor de paginación inválido.")
    return decoded
