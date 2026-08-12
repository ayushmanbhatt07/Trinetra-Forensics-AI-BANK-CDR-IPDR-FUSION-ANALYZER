"""Standard uvicorn entry point.

Run from the backend/ directory:
    uvicorn main:app --reload --port 8000
or from the repo root:
    uvicorn backend.main:app --reload --port 8000
"""

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.api import app  # noqa: E402, F401
