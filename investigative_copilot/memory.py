"""Continuous-learning memory for the Investigative Co-Pilot.

The copilot SQLite DB is rebuilt in-memory per bundle, so conversational
memory lives here instead: a small file-backed JSON store keyed by a bundle
fingerprint. Each bundle learns its own digest (entity census, top
scenarios, NCRP hit list) plus the recent Q&A turns, and that context is
injected into every LLM system prompt — the model therefore "knows" what
was already investigated and what the corpus contains, without re-reading
the data. Memory survives server restarts and persists across ingests of
the same bundle fingerprint.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from backend import config

logger = logging.getLogger(__name__)

_DIGEST_KEY = "bundle_digest"
_CHAT_TURNS_KEY = "chat_turns"
_MAX_CHAT_TURNS = 8


def _fingerprint(bundle: Optional[Dict[str, Any]]) -> str:
    if not bundle:
        return "empty"
    return "|".join(str(len(bundle.get(k) or [])) for k in
                    ("bank", "cdr", "ipdr", "complaints", "subscribers"))


def build_bundle_digest(bundle: Optional[Dict[str, Any]]) -> str:
    """Runs entirely on already-computed bundle fields (no heavy analysis).

    Produces a short corpus brief the LLM reads before answering, so every
    query is answered against the currently loaded dataset instead of
    generic training knowledge.
    """
    if not bundle:
        return "No dataset is currently loaded."
    bank = bundle.get("bank") or []
    cdr = bundle.get("cdr") or []
    ipdr = bundle.get("ipdr") or []
    complaints = bundle.get("complaints") or []
    subscribers = bundle.get("subscribers") or []
    modes: Dict[str, int] = {}
    states: Dict[str, int] = {}
    top_recv: Dict[str, int] = {}
    for r in bank:
        m = str(r.get("mode") or "")
        if m:
            modes[m] = modes.get(m, 0) + 1
        acc = str(r.get("receiver_account") or "")
        if acc:
            top_recv[acc] = top_recv.get(acc, 0) + 1
    for c in cdr:
        st = str(c.get("roaming_circle") or "").strip()
        if st:
            states[st] = states.get(st, 0) + 1
    top_modes = ", ".join(f"{k} x{v}" for k, v in
                          sorted(modes.items(), key=lambda x: -x[1])[:5])
    top_accs = ", ".join(f"{k} x{v}" for k, v in
                         sorted(top_recv.items(), key=lambda x: -x[1])[:5])
    ncrp = len(complaints)
    return (
        f"Currently loaded corpus (fingerprint {_fingerprint(bundle)}): "
        f"{len(bank)} bank transactions, {len(cdr)} CDR call records, "
        f"{len(ipdr)} IPDR internet sessions, {ncrp} NCRP complaints, "
        f"{len(subscribers)} subscriber records. "
        f"Top transaction modes: {top_modes or 'n/a'}. "
        f"Top receiving accounts: {top_accs or 'n/a'}. "
        f"CDR roaming circles seen: {', '.join(sorted(states)) or 'n/a'}."
        f" NCRP complaints name suspected fraud beneficiaries; "
        f"cross-check every flagged account against the complaints ledger."
    )


class MemoryStore:
    """File-backed key/value memory for one bundle fingerprint."""

    def __init__(self, bundle: Optional[Dict[str, Any]] = None,
                 path: Optional[Path] = None, username: str = "default") -> None:
        self._lock = threading.RLock()
        self.username = username
        self.fingerprint = _fingerprint(bundle)
        self.path = path or (config.data_dir() / "copilot_memory.json")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data: Dict[str, Any] = self._load().get(self.username, {})
        self._loaded_fp = self.fingerprint
        if bundle is not None and _DIGEST_KEY not in self._data:
            self.set(_DIGEST_KEY, build_bundle_digest(bundle))

    def _load(self) -> Dict[str, Any]:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                return data if isinstance(data, dict) else {}
        except (OSError, ValueError) as e:
            logger.warning("Failed to read copilot memory %s: %s", self.path, e)
        return {}

    def _save(self) -> None:
        try:
            all_data = self._load()
            all_data[self.username] = self._data
            self.path.write_text(json.dumps(all_data, ensure_ascii=False,
                                            indent=1), encoding="utf-8")
        except OSError as e:
            logger.warning("Failed to write copilot memory %s: %s",
                           self.path, e)

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._data[key] = value
            self._save()

    def refresh(self, bundle: Optional[Dict[str, Any]]) -> str:
        """Re-learn the corpus digest from the current bundle. Called on every
        ingestion so the LLM always reasons on the freshest data even when the
        bundle fingerprint (counts) is unchanged."""
        digest = build_bundle_digest(bundle)
        with self._lock:
            if self._data.get(_DIGEST_KEY) != digest:
                self._data[_DIGEST_KEY] = digest
                self._save()
        return digest

    def digest(self) -> str:
        return str(self.get(_DIGEST_KEY, "") or "")

    def recent_chat(self) -> List[Dict[str, str]]:
        return list(self.get(_CHAT_TURNS_KEY) or [])

    def remember_turn(self, user_query: str, summary: str) -> None:
        """Appends one Q&A turn, keeping only the most recent turns."""
        if not (user_query and summary):
            return
        with self._lock:
            turns = list(self.get(_CHAT_TURNS_KEY) or [])
            turns.append({"user": user_query[:400], "assistant": summary[:600]})
            self._data[_CHAT_TURNS_KEY] = turns[-_MAX_CHAT_TURNS:]
            self._save()

    def memory_block(self) -> str:
        """The context block injected into the LLM system prompt."""
        lines = [f"CORPUS BRIEF (learned from the loaded dataset):\n{self.digest()}"]
        turns = self.recent_chat()
        if turns:
            chat_lines = []
            for i, t in enumerate(turns, 1):
                chat_lines.append(
                    f"Turn {i}: investigator asked \"{t['user']}\" "
                    f"and the analysis concluded: {t['assistant']}")
            lines.append("CONVERSATION MEMORY (what we already investigated "
                         "in this case — use it for continuity, do not repeat "
                         "or contradict it without new evidence):\n" +
                         "\n".join(chat_lines))
        return "\n\n".join(lines)
