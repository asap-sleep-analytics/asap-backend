import base64

import pytest

from app.models.pagination import (
    CursorPage,
    decode_cursor,
    decode_cursor_parts,
    encode_cursor,
    encode_cursor_parts,
)


def test_cursor_roundtrip_utf8() -> None:
    for value in ["2026-01-15T10:30:00.123456", "clave-simple", "año_ñ_ü emojis 😴"]:
        assert decode_cursor(encode_cursor(value)) == value


def test_encode_cursor_devuelve_base64_urlsafe() -> None:
    encoded = encode_cursor("2026-01-15T10:30:00")
    decoded = base64.urlsafe_b64decode(encoded.encode("ascii")).decode("utf-8")
    assert decoded == "2026-01-15T10:30:00"


@pytest.mark.parametrize(
    "raw",
    [
        "not-base64!!!",
        "%%%",
        "aGVsbG8",
        "",  # vacío decodifica pero debe rechazarse
    ],
)
def test_decode_cursor_rechaza_cadenas_invalidas(raw: str) -> None:
    with pytest.raises(ValueError, match="Cursor de paginación inválido."):
        decode_cursor(raw)


def test_decode_cursor_rechaza_base64_de_ruta_invalida() -> None:
    # Base64 mal formado que no decodifica a texto UTF-8
    with pytest.raises(ValueError, match="Cursor de paginación inválido."):
        decode_cursor("////")


def test_cursor_page_model() -> None:
    page = CursorPage(items=["a", "b"], next_cursor="Y3Vyc29y", has_more=True)
    assert page.items == ["a", "b"]
    assert page.next_cursor == "Y3Vyc29y"
    assert page.has_more is True

    empty = CursorPage(items=[], next_cursor=None, has_more=False)
    assert empty.has_more is False
    assert empty.next_cursor is None


def test_cursor_parts_roundtrip() -> None:
    parts = ["2026-01-15T10:30:00.123456", "uuid-abc-123"]
    encoded = encode_cursor_parts(parts)
    assert decode_cursor_parts(encoded) == parts


def test_cursor_parts_roundtrip_unicode() -> None:
    parts = ["2026-02-01T00:00:00+00:00", "ñ u ü 😴"]
    assert decode_cursor_parts(encode_cursor_parts(parts)) == parts


@pytest.mark.parametrize(
    "raw",
    [
        "not-base64!!!",
        "aGVsbG8",
        "W10=",  # "[]" lista vacía
        "W251bGxd",  # "[null]" no es una lista de strings
        "WyJzb2xvIiwgNDJd",  # '["solo", 42]' incluye un entero
    ],
)
def test_decode_cursor_parts_rechaza_invalidos(raw: str) -> None:
    with pytest.raises(ValueError, match="Cursor de paginación inválido."):
        decode_cursor_parts(raw)
