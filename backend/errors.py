"""Typed exceptions shared by detection, parsing and the pipeline.

Hierarchy:
    BackendError          base
    ├─ DetectError         format detection failed / low confidence
    ├─ ParseError          a file is parseable but the parser failed
    │   └─ SkipFileError   gracefully skipped (scanned PDF, password-protected,
    │                      unsupported image format, no records)
    │       └─ AskUser     low-confidence detection — caller should ask
    └─ ValidationError     ground-truth comparison problem

Skip semantics: the pipeline treats SkipFileError as "report skipped, not an
error". DetectError is logged and the file lands in errors only when it is a
supported type that could not be classified; otherwise it is skipped.
"""

from __future__ import annotations


class BackendError(Exception):
    """Base class for all engine errors."""


class DetectError(BackendError):
    """Format detection failed."""


class ParseError(BackendError):
    """A supported file could not be parsed."""


class SkipFileError(ParseError):
    """File intentionally skipped (scanned OCR, encrypted, unsupported image).

    `reason` is a short stable machine-readable code, `detail` a human
    explanation surfaced in the ingest report.
    """

    def __init__(self, reason: str = "skipped", detail: str = ""):
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


class AskUser(SkipFileError):
    """Detection confidence too low — the caller should ask the user to pick.

    Carries the candidate formats so the UI can offer them.
    """

    def __init__(self, candidates: list[dict], detail: str = ""):
        self.candidates = candidates
        super().__init__("ask_user", detail or "low-confidence format detection")


class ValidationError(BackendError):
    """Ground-truth comparison configuration/processing problem."""
