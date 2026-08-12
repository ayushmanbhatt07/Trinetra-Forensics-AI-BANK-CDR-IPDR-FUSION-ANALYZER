"""Parser plugins: registry-driven, one parser per detected format id.

    parsers.parse(format_id, path)     -> ParseResult
    parsers.get_parser(format_id)      -> BaseParser | None
    parsers.registered_formats()       -> {format_id: class_name}

Backwards compatibility: backend.pipeline.parse_file still drives ingestion
through these plugins; the old v2 modules remain as the row engines.
"""

from __future__ import annotations

from .base import BaseParser, ParseResult  # noqa: F401
from .registry import (  # noqa: F401
    get_parser, parse, register, registered_formats, require_parser,
)
from . import bank, cdr, complaint, ipdr, subscriber  # noqa: F401,E402

__all__ = ["BaseParser", "ParseResult", "get_parser", "parse", "register",
           "registered_formats", "require_parser"]
