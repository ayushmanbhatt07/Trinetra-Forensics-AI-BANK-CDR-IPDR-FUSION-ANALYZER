"""Registry: format_id -> parser instance, with lazy discovery.

Adding a parser: subclass BaseParser, set format_id/dataset, register via
    registry.register(MyParser)
in the module's import (registry imports all format modules automatically).
"""

from __future__ import annotations

from ..errors import ParseError
from .base import BaseParser, ParseResult

_REGISTRY: dict[str, BaseParser] = {}
_LOADED = False


def register(cls: type[BaseParser]) -> type[BaseParser]:
    if not cls.format_id:
        raise ValueError(f"{cls.__name__} must define format_id")
    _REGISTRY[cls.format_id] = cls()
    return cls


def _load_all() -> None:
    global _LOADED
    if _LOADED:
        return
    from . import (bank, cdr, complaint, ipdr, subscriber, synthetic)  # noqa: F401
    _LOADED = True


def get_parser(format_id: str) -> BaseParser | None:
    _load_all()
    return _REGISTRY.get(format_id)


def require_parser(format_id: str) -> BaseParser:
    p = get_parser(format_id)
    if p is None:
        raise ParseError(
            f"no parser registered for format '{format_id}'",
            "supported: " + ", ".join(sorted(_REGISTRY)))
    return p


def parse(format_id: str, path: str, context: dict | None = None) -> ParseResult:
    return require_parser(format_id).parse(path, context)


def registered_formats() -> dict[str, str]:
    _load_all()
    return {fid: type(p).__name__ for fid, p in sorted(_REGISTRY.items())}
