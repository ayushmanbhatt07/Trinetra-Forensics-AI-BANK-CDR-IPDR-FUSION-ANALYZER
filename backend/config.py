"""Runtime configuration.

All settings are overridable via `APP_*` environment variables so the
same image runs in dev, staging and production without code changes.

Additions in v3 (pipeline knobs):
    APP_CORRELATION_WINDOW_SEC  temporal coincidence window (default 3600)
    APP_INGEST_TIMEOUT_SEC      per-file parse timeout (default 120)
    APP_PARSER_THREADS          parallel parser workers (default 4)
    APP_DETECT_MIN_CONFIDENCE   below this -> AskUser (default 0.55)
    APP_ANOMALY_CONTAMINATION   ML outlier fraction (default 0.05)
    APP_MAX_UPLOAD_FILES        multipart upload cap (default 50)
    APP_LOG_FORMAT              text | json (default text)
    APP_CASE_DIR                case evidence root (default data/cases)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent / ".env")
    load_dotenv()
except ImportError:
    pass

ENV_PREFIX = "APP_"

DEFAULTS = {
    "DATA_DIR": "./data",
    "CASE_DIR": "./data/cases",
    "LOG_LEVEL": "INFO",
    "LOG_FORMAT": "text",
    "CORS_ORIGINS": "http://localhost:3000,http://127.0.0.1:3000",
    "API_HOST": "0.0.0.0",
    "API_PORT": "8000",
    "STR_FILE_TTL_HOURS": "24",
    "TOKEN_TTL_HOURS": "12",
    "ALLOW_SIGNUP": "1",
    "CORRELATION_WINDOW_SEC": "3600",
    "INGEST_TIMEOUT_SEC": "120",
    "PARSER_THREADS": "4",
    "DETECT_MIN_CONFIDENCE": "0.55",
    "ANOMALY_CONTAMINATION": "0.05",
    "MAX_UPLOAD_FILES": "50",
    "CLEAR_ON_STARTUP": "1",
}


def _get(key: str, default: str | None = None) -> str:
    return os.environ.get(ENV_PREFIX + key, default if default is not None
                          else DEFAULTS[key])


def _int(key: str, default: int) -> int:
    try:
        return int(_get(key))
    except ValueError:
        return default


def _float(key: str, default: float) -> float:
    try:
        return float(_get(key))
    except ValueError:
        return default


def data_dir() -> Path:
    raw = _get("DATA_DIR")
    if not os.path.isabs(raw):
        if os.path.exists("/app/data"):
            d = Path("/app/data").resolve()
        else:
            base = Path(__file__).resolve().parent
            d = (base / raw).expanduser().resolve()
    else:
        d = Path(raw).expanduser().resolve()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        import tempfile
        d = Path(tempfile.gettempdir()) / "trinetra_data"
        d.mkdir(parents=True, exist_ok=True)
    return d


def case_dir() -> Path:
    raw = _get("CASE_DIR")
    if not os.path.isabs(raw):
        if os.path.exists("/app/data/cases"):
            d = Path("/app/data/cases").resolve()
        else:
            base = Path(__file__).resolve().parent
            d = (base / raw).expanduser().resolve()
    else:
        d = Path(raw).expanduser().resolve()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        import tempfile
        d = Path(tempfile.gettempdir()) / "trinetra_data" / "cases"
        d.mkdir(parents=True, exist_ok=True)
    return d


def cors_origins() -> list[str]:
    return [o.strip() for o in _get("CORS_ORIGINS").split(",") if o.strip()]


def api_host() -> str:
    return _get("API_HOST")


def api_port() -> int:
    return _int("API_PORT", 8000)


def str_file_ttl_hours() -> int:
    return max(1, _int("STR_FILE_TTL_HOURS", 24))


def token_ttl_hours() -> float:
    return max(1.0, _float("TOKEN_TTL_HOURS", 12.0))


def allow_signup() -> bool:
    return _get("ALLOW_SIGNUP").lower() in ("1", "true", "yes")


def correlation_window_sec() -> int:
    return max(60, _int("CORRELATION_WINDOW_SEC", 3600))


def ingest_timeout_sec() -> int:
    return max(10, _int("INGEST_TIMEOUT_SEC", 120))


def max_workers() -> int:
    """Determine the maximum thread pool workers based on CPU core count or APP_MAX_WORKERS."""
    env_val = os.environ.get("APP_MAX_WORKERS")
    if env_val:
        try:
            return max(1, int(env_val))
        except ValueError:
            pass
    cpu_cnt = os.cpu_count() or 1
    return max(1, min(2, cpu_cnt))


def parser_threads() -> int:
    return min(max_workers(), max(1, _int("PARSER_THREADS", 4)))


def detect_min_confidence() -> float:
    return min(1.0, max(0.0, _float("DETECT_MIN_CONFIDENCE", 0.55)))


def anomaly_contamination() -> float:
    return min(0.5, max(0.01, _float("ANOMALY_CONTAMINATION", 0.05)))


def max_upload_files() -> int:
    return max(1, _int("MAX_UPLOAD_FILES", 50))


def clear_on_startup() -> bool:
    return _get("CLEAR_ON_STARTUP", "1").lower() in ("1", "true", "yes", "on")


def groq_keys() -> list[str]:
    """All configured Groq API keys, de-duplicated, in fallback order.

    Supports rotation to avoid rate limits.
    Automatically discovers:
      - Any env var starting with GROQ_API_KEY (e.g. GROQ_API_KEY, GROQ_API_KEY_1, GROQ_API_KEY_2...)
      - Any env var starting with APP_GROQ_API_KEY
      - GROQ_KEY, GROQ_KEYS, GROQ_API_KEYS (comma or space separated)
      - OPEN_ROUTER_KEY_*, OPENROUTER_API_KEY, OPENAI_API_KEY
      - Strips quotes (", '), whitespace, and trailing commas.
      - Re-checks .env files across all common root and backend paths if empty.
    """
    out = []

    def _extract_from_env():
        # Check all possible environment variable name patterns
        for key_name, val in list(os.environ.items()):
            k_upper = key_name.upper()
            if (
                k_upper.startswith("GROQ_API_KEY")
                or k_upper.startswith("APP_GROQ_API_KEY")
                or k_upper in ("GROQ_KEY", "GROQ_KEYS", "GROQ_API_KEYS")
                or k_upper.startswith("OPEN_ROUTER_KEY")
                or k_upper in ("OPENROUTER_API_KEY", "OPENAI_API_KEY")
            ):
                if not val:
                    continue
                # Split comma/semicolon/whitespace separated lists
                parts = [p.strip() for p in re.split(r"[,;\n\r\t]+", str(val)) if p.strip()]
                for raw in parts:
                    clean_k = raw.strip("\"'` \t\r\n")
                    if clean_k and clean_k not in out:
                        out.append(clean_k)

    import re
    _extract_from_env()

    # If no keys discovered in os.environ yet, try loading all potential .env paths
    if not out:
        env_candidates = [
            Path.cwd() / ".env",
            Path.cwd() / "backend" / ".env",
            Path(__file__).resolve().parent / ".env",
            Path(__file__).resolve().parent.parent / ".env",
            Path("/app/.env"),
            Path("/app/backend/.env"),
            Path("/data/.env"),
            Path("/data/backend.env"),
        ]
        try:
            from dotenv import load_dotenv
            for cand in env_candidates:
                if cand.exists():
                    load_dotenv(cand, override=False)
            _extract_from_env()
        except Exception:
            pass

    return out


# Backwards-compat alias (remove after all callers are migrated)
open_router_keys = groq_keys


def log_format() -> str:
    return _get("LOG_FORMAT").lower()


def log_level() -> int:
    return getattr(logging, _get("LOG_LEVEL").upper(), logging.INFO)


def setup_logging(name: str = "backend") -> logging.Logger:
    """v2-compat logger (structured log.py supersedes this for new code)."""
    lg = logging.getLogger(name)
    lg.setLevel(log_level())
    if not lg.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s"))
        lg.addHandler(h)
    lg.propagate = False
    return lg


# v2-compat attribute; log.py replaces it with the structured logger on import.
log = setup_logging()
