from pydantic import BaseModel


class CursorPage(BaseModel):
    items: list
    next_cursor: str | None
    has_more: bool


def encode_cursor(value: str) -> str:
    import base64
    return base64.urlsafe_b64encode(value.encode()).decode()


def decode_cursor(value: str) -> str:
    import base64
    return base64.urlsafe_b64decode(value.encode()).decode()
