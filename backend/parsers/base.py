"""Parser plugin framework: base classes and result contract.

Each format family ships as a BaseParser subclass registered in registry.py.
Parsers emit v2-shape records (pre-canonicalisation); normalise.py maps them
onto the canonical schema.  A parser must never raise for bad rows — it
skips them and reports counts in meta.

Inputs:  path + optional context (detection result, source metadata).
Outputs: ParseResult(records, meta, format_id, dataset).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from ..errors import ParseError, SkipFileError


@dataclass
class ParseResult:
    records: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    format_id: str = ""
    dataset: str = ""

    def with_meta(self, **updates) -> "ParseResult":
        self.meta.update(updates)
        return self


class BaseParser(ABC):
    """One parser per detected format id."""

    format_id: str = ""
    dataset: str = ""
    #: hints shown by the API layer / detection UI
    description: str = ""

    @abstractmethod
    def parse(self, path: str, context: dict | None = None) -> ParseResult:
        """Parse `path` into ParseResult. Raise ParseError on fatal issues,
        SkipFileError for content that cannot be parsed (scanned, protected)."""

    def can_parse(self, path: str) -> bool:
        """Cheap pre-check (extension-based); default accepts everything and
        lets parse() decide."""
        return True

    # -- helpers shared by concrete parsers --------------------------------

    @staticmethod
    def skip(reason: str, detail: str = "") -> ParseResult:
        raise SkipFileError(reason, detail)

    @staticmethod
    def fail(reason: str, detail: str = "") -> ParseResult:
        raise ParseError(reason, detail)
