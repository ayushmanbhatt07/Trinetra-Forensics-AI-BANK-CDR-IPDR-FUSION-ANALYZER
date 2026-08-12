"""Structured logging.

Channels:
    backend          engine-wide log
    backend.parser   per-parser log (record counts, skipped, issues)
    backend.pipeline ingest orchestrator
    backend.correlation rule engine
    backend.api      HTTP layer

`APP_LOG_FORMAT=json` emits single-line JSON records (machine-parseable
for log shippers); `text` (default) keeps human-readable `k=v` lines. Both
carry the same structured `extra` fields: module, parser, file, dataset,
records, duration_ms, error, reason.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone

from . import config


class _StructuredFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = f"{record.asctime} {record.levelname} {record.name}: {record.getMessage()}"
        extras = getattr(record, "extra_fields", None)
        if extras:
            parts = " ".join(f"{k}={v}" for k, v in extras.items())
            base += f" [{parts}]"
        return base


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }
        extras = getattr(record, "extra_fields", None)
        if extras:
            payload.update(extras)
        if record.exc_info and record.exc_info[0] is not None:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def _handler() -> logging.Handler:
    h = logging.StreamHandler(sys.stderr)
    if config.log_format() == "json":
        h.setFormatter(_JsonFormatter())
    else:
        f = _StructuredFormatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s")
        h.setFormatter(f)
    return h


_loggers: dict[str, logging.Logger] = {}


def get_logger(name: str = "backend") -> logging.Logger:
    """Return the named logger, configured once (idempotent)."""
    if name in _loggers:
        return _loggers[name]
    log = logging.getLogger(name)
    log.setLevel(config.log_level())
    if not log.handlers:
        log.addHandler(_handler())
    log.propagate = False
    _loggers[name] = log
    return log


def _log_with_extras(logger: logging.Logger, level: int, msg: str,
                     **extras) -> None:
    if not logger.isEnabledFor(level):
        return
    extras = {k: v for k, v in extras.items() if v is not None}
    if extras:
        logger.log(level, msg, extra={"extra_fields": extras})
    else:
        logger.log(level, msg)


def log_parser(name: str, file: str, dataset: str, fmt: str, records: int,
               duration_ms: float, status: str = "ok", error: str = "",
               **more) -> None:
    """Structured per-file parser log line."""
    log = get_logger("backend.parser")
    level = logging.ERROR if status == "error" else \
        logging.WARNING if status == "skipped" else logging.INFO
    _log_with_extras(log, level,
                     f"{status}: {name} -> {records} records",
                     file=file, dataset=dataset, format=fmt, records=records,
                     duration_ms=int(duration_ms), status=status,
                     error=error or None, **more)


def log_pipeline(msg: str, **extras) -> None:
    _log_with_extras(get_logger("backend.pipeline"), logging.INFO, msg, **extras)


def log_correlation(msg: str, **extras) -> None:
    _log_with_extras(get_logger("backend.correlation"), logging.INFO, msg, **extras)


def log_api(msg: str, level: int = logging.INFO, **extras) -> None:
    _log_with_extras(get_logger("backend.api"), level, msg, **extras)


# Default engine logger (kept for backwards compatibility with v2 modules).
log = get_logger("backend")

# Replace config.log with the structured logger so v2 callers (`config.log`)
# benefit from the same formatting.
config.log = log


def setup_logging(name: str = "backend") -> logging.Logger:
    """v2-compat entry point."""
    return get_logger(name)
