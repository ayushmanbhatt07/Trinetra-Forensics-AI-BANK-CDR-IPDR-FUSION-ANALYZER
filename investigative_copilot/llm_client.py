"""Centralized Multi-Key & Multi-Model LLM Client (Groq).

Implements a strict failover matrix:
  KEY 1 -> KEY 2 -> KEY 3 -> KEY 4 -> KEY 5 (all discovered keys)
  For each key: Model 1 -> Model 2 -> Model 3 ... (all configured models)
  Automatic transient error retry with exponential backoff.
  Deterministic mode is reached ONLY after all keys, models, and retries are exhausted.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

from backend import config

logger = logging.getLogger(__name__)

# Primary model: High-accuracy, high-capacity reasoning / versatility
DEFAULT_MODEL = "llama-3.3-70b-versatile"

# Fallback models ordered by quality, capability, and token limits
FALLBACK_MODELS = [
    "llama-3.3-70b-versatile",       # LLaMA 3.3 70B (primary versatile)
    "openai/gpt-oss-120b",           # High-capacity 120B reasoning
    "openai/gpt-oss-20b",            # 20B fast model
    "llama-3.1-8b-instant",          # LLaMA 3.1 8B (ultra-fast instant fallback)
    "qwen/qwen3.6-27b",              # Qwen 27B reasoning
    "groq/compound",                 # Groq Compound
    "groq/compound-mini",            # Groq Compound Mini
    "allam-2-7b",                    # Fast 7B model
    "canopylabs/orpheus-v1-english", # Fast English model
]

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


class TokenTracker:
    """Mathematical token tracking engine for Groq LLMs."""
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.last_prompt_tokens: int = 0
        self.last_completion_tokens: int = 0
        self.last_total_tokens: int = 0
        self._window_records: List[Tuple[float, int]] = []
        self.active_model: str = DEFAULT_MODEL
        self.groq_header_remaining_tokens: Optional[int] = None
        self.groq_header_limit_tokens: Optional[int] = None

    def record_usage(self, prompt_tokens: int, completion_tokens: int, model: str,
                     header_remaining: Optional[int] = None, header_limit: Optional[int] = None) -> None:
        now = time.time()
        total = prompt_tokens + completion_tokens
        with self._lock:
            self.last_prompt_tokens = prompt_tokens
            self.last_completion_tokens = completion_tokens
            self.last_total_tokens = total
            self.active_model = model
            if header_remaining is not None:
                self.groq_header_remaining_tokens = header_remaining
            if header_limit is not None:
                self.groq_header_limit_tokens = header_limit
            self._window_records.append((now, total))
            self._window_records = [(t, tok) for t, tok in self._window_records if now - t <= 60.0]

    def get_stats(self) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            self._window_records = [(t, tok) for t, tok in self._window_records if now - t <= 60.0]
            used_last_min = sum(tok for _, tok in self._window_records)
            
            keys = config.groq_keys()
            num_keys = max(1, len(keys))
            
            model = (self.active_model or DEFAULT_MODEL).lower()
            if "120b" in model or "20b" in model:
                base_tpm = 250000
            elif "70b" in model:
                base_tpm = 30000
            elif "8b" in model:
                base_tpm = 30000
            elif "qwen" in model:
                base_tpm = 15000
            else:
                base_tpm = 30000

            total_tpm_capacity = base_tpm * num_keys

            if self.groq_header_remaining_tokens is not None and self.groq_header_remaining_tokens > 0:
                remaining_tpm = self.groq_header_remaining_tokens * num_keys
            else:
                remaining_tpm = max(0, total_tpm_capacity - used_last_min)

            pct_remaining = round((remaining_tpm / max(1, total_tpm_capacity)) * 100, 1)
            pct_remaining = min(100.0, max(0.0, pct_remaining))

            return {
                "active_model": self.active_model,
                "active_keys_count": num_keys,
                "base_tpm_limit": base_tpm,
                "total_tpm_capacity": total_tpm_capacity,
                "used_last_minute": used_last_min,
                "remaining_tpm": remaining_tpm,
                "pct_remaining": pct_remaining,
                "last_query": {
                    "prompt_tokens": self.last_prompt_tokens,
                    "completion_tokens": self.last_completion_tokens,
                    "total_tokens": self.last_total_tokens,
                }
            }


token_tracker = TokenTracker()


def _mask_key(key: str) -> str:
    if not key:
        return "NO_KEY"
    if len(key) > 8:
        return f"{key[:4]}...{key[-4:]}"
    return "gsk_****"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pulls the first balanced JSON object out of an LLM reply."""
    if not text:
        return None
    stripped = text.strip()
    # Strip <think>...</think> or <thought>...</thought> tags
    stripped = re.sub(r"<(?:think|thought)>[\s\S]*?</(?:think|thought)>", "", stripped).strip()
    # Strip markdown code fences
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    # Fast path
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Bracket matching fallback
    start = stripped.find("{")
    if start == -1:
        return None
    depth = 0
    for idx in range(start, len(stripped)):
        ch = stripped[idx]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = stripped[start:idx + 1]
                try:
                    res = json.loads(candidate)
                    if isinstance(res, dict):
                        return res
                except Exception:
                    pass
                break
    return None


class LLMKeyManager:
    """Centralized state and failover manager for LLM API keys and models."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        # Map: (key_id, model) -> state dict
        self._state: Dict[Tuple[str, str], Dict[str, Any]] = {}

    def get_state(self, key_id: str, model: str) -> Dict[str, Any]:
        with self._lock:
            key_tuple = (key_id, model)
            if key_tuple not in self._state:
                self._state[key_tuple] = {
                    "key_id": key_id,
                    "model": model,
                    "status": "ACTIVE",
                    "last_error": None,
                    "error_type": None,
                    "quota_exhausted": False,
                    "temporarily_unavailable": False,
                    "permanently_unavailable": False,
                    "last_success": None,
                    "retry_after": 0.0,
                    "consecutive_failures": 0,
                }
            return dict(self._state[key_tuple])

    def is_usable(self, key_id: str, model: str) -> bool:
        with self._lock:
            s = self._state.get((key_id, model))
            if not s:
                return True
            if s.get("permanently_unavailable"):
                return False
            if s.get("quota_exhausted") or s.get("temporarily_unavailable"):
                if time.time() < s.get("retry_after", 0.0):
                    return False
                # Cooldown expired -> mark usable again
                s["quota_exhausted"] = False
                s["temporarily_unavailable"] = False
                s["status"] = "ACTIVE"
            return True

    def mark_success(self, key_id: str, model: str) -> None:
        with self._lock:
            key_tuple = (key_id, model)
            s = self._state.setdefault(key_tuple, {
                "key_id": key_id, "model": model,
            })
            s["status"] = "ACTIVE"
            s["last_success"] = time.time()
            s["last_error"] = None
            s["error_type"] = None
            s["quota_exhausted"] = False
            s["temporarily_unavailable"] = False
            s["permanently_unavailable"] = False
            s["consecutive_failures"] = 0

    def mark_failure(self, key_id: str, model: str, error_msg: str, status_code: Optional[int] = None) -> None:
        now = time.time()
        err_lower = (error_msg or "").lower()
        with self._lock:
            key_tuple = (key_id, model)
            s = self._state.setdefault(key_tuple, {
                "key_id": key_id, "model": model,
            })
            s["last_error"] = error_msg
            s["consecutive_failures"] = s.get("consecutive_failures", 0) + 1

            if status_code == 429 or "rate_limit" in err_lower or "quota" in err_lower or "tokens per minute" in err_lower:
                s["status"] = "QUOTA_EXHAUSTED"
                s["error_type"] = "rate_limit_or_quota"
                s["quota_exhausted"] = True
                s["retry_after"] = now + 60.0  # 60s cooldown before retrying this key/model
            elif status_code in (404, 400) and any(sig in err_lower for sig in ("model_not_found", "decommission", "does not exist", "unsupported")):
                s["status"] = "PERMANENTLY_UNAVAILABLE"
                s["error_type"] = "model_unavailable"
                s["permanently_unavailable"] = True
            elif status_code == 401 or "invalid_api_key" in err_lower or "unauthorized" in err_lower:
                s["status"] = "PERMANENTLY_UNAVAILABLE"
                s["error_type"] = "auth_failure"
                s["permanently_unavailable"] = True
            else:
                s["status"] = "TEMPORARILY_UNAVAILABLE"
                s["error_type"] = f"http_{status_code}" if status_code else "transient_error"
                s["temporarily_unavailable"] = True
                s["retry_after"] = now + 10.0


key_manager = LLMKeyManager()


class LlmClient:
    """Zero-dependency HTTP client for Groq LLMs with 5-key failover matrix."""

    def __init__(self, active_model: Optional[str] = None, request_timeout: float = 45.0) -> None:
        self.active_model = active_model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.request_timeout = request_timeout
        self._last_latency = 0

    @property
    def latency_ms(self) -> int:
        return self._last_latency

    def has_provider(self) -> bool:
        """True when at least one Groq API key is configured."""
        return bool(config.groq_keys())

    def generate_json(self, system_prompt: str, user_content: str,
                      temperature: float = 0.1
                      ) -> Tuple[bool, Optional[Dict[str, Any]], Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "provider": "", "model": "", "key_id": "", "latency_ms": 0,
            "error": "", "mode": "llm", "all_keys_exhausted": False,
        }
        keys = config.groq_keys()

        if not keys:
            meta["error"] = "No Groq API keys configured in environment."
            meta["mode"] = "deterministic_fallback"
            meta["all_keys_exhausted"] = True
            logger.warning("[LLM Client] No API keys configured — deterministic fallback enabled.")
            return False, None, meta

        ok, parsed, err, used_key_id, used_model = self._call_groq_failover_matrix(
            system_prompt, user_content, temperature, json_mode=True, keys=keys
        )
        meta["latency_ms"] = self.latency_ms

        if ok and parsed:
            meta["provider"] = "groq"
            meta["model"] = used_model
            meta["key_id"] = used_key_id
            meta["mode"] = "llm"
            return True, parsed, meta

        meta["error"] = err
        meta["mode"] = "deterministic_fallback"
        meta["all_keys_exhausted"] = True
        logger.warning("[LLM Failover Exhausted] All configured keys and models failed (%s). Activating deterministic fallback.", err)
        return False, None, meta

    def _call_groq_failover_matrix(self, system_prompt: str, user_content: str,
                                   temperature: float, json_mode: bool,
                                   keys: List[str]
                                   ) -> Tuple[bool, Optional[Dict[str, Any]], str, str, str]:
        """Iterates through all 5 keys and all configured models in a strict failover matrix."""
        models_to_try = [self.active_model] + [m for m in FALLBACK_MODELS if m != self.active_model]
        last_err = "No models or keys available"

        for key_idx, key in enumerate(keys):
            key_id = f"KEY_{key_idx + 1}"
            key_masked = _mask_key(key)

            for model in models_to_try:
                # Check if this (key, model) is currently usable
                if not key_manager.is_usable(key_id, model):
                    continue

                payload: Dict[str, Any] = {
                    "model": model,
                    "temperature": temperature,
                    "max_tokens": 4096,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content},
                    ],
                }
                if json_mode:
                    payload["response_format"] = {"type": "json_object"}

                logger.info(f"[LLM Request] Invoking {key_id} ({key_masked}) with model '{model}'...")

                # Transient retry loop (up to 2 attempts for 5xx/connection drops)
                for attempt in range(2):
                    ok, parsed, err, status_code = self._post_json(
                        _GROQ_URL, payload, key, self.request_timeout
                    )

                    # If JSON mode failed with 400 (unsupported response_format), retry without response_format
                    if not ok and json_mode and status_code == 400:
                        payload_no_json = dict(payload)
                        payload_no_json.pop("response_format", None)
                        ok, parsed, err, status_code = self._post_json(
                            _GROQ_URL, payload_no_json, key, self.request_timeout
                        )

                    if ok and parsed:
                        key_manager.mark_success(key_id, model)
                        self.active_model = model
                        latency_sec = self.latency_ms / 1000.0
                        logger.info(f"[LLM Success] {key_id} | Model '{model}' -> SUCCEEDED in {latency_sec:.2f}s")
                        return True, parsed, "", key_id, model

                    # If transient failure (5xx or connection error), apply backoff before retry attempt
                    if status_code and status_code >= 500 and attempt == 0:
                        logger.warning(f"[LLM Transient Error] {key_id} | Model '{model}' -> HTTP {status_code} ({err}). Retrying...")
                        time.sleep(0.1)
                        continue
                    break

                # Record failure for state tracking
                key_manager.mark_failure(key_id, model, err, status_code)
                last_err = f"{key_id} | {model}: {err}"
                logger.warning(f"[LLM Failure] {key_id} ({key_masked}) | Model '{model}' FAILED: {err}")

                # If auth failure on this key, skip all other models for this key immediately
                if status_code == 401 or "invalid_api_key" in (err or "").lower():
                    logger.warning(f"[LLM Key Invalid] {key_id} credentials rejected. Rotating to next key...")
                    break

                # If rate-limited / quota exhausted on this key, rotate to next key immediately
                if status_code == 429 or "rate_limit" in (err or "").lower() or "quota" in (err or "").lower():
                    logger.warning(f"[LLM Key Quota] {key_id} rate-limited. Rotating to next key...")
                    break

        return False, None, last_err, "", ""

    def _post_json(self, url: str, payload: Dict[str, Any], key: str,
                   timeout: float
                   ) -> Tuple[bool, Optional[Dict[str, Any]], str, Optional[int]]:
        t0 = time.monotonic()
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(url, json=payload, timeout=timeout, headers=headers)
        except requests.RequestException as e:
            self._last_latency = int((time.monotonic() - t0) * 1000)
            return False, None, f"Transport error: {type(e).__name__} ({str(e)})", None

        self._last_latency = int((time.monotonic() - t0) * 1000)
        status_code = resp.status_code

        try:
            data = resp.json()
        except ValueError:
            return False, None, f"HTTP {status_code}: non-JSON reply", status_code

        if status_code != 200:
            msg = str(data.get("error", data))[:200] if isinstance(data, dict) else str(data)[:200]
            return False, None, f"HTTP {status_code}: {msg}", status_code

        # Extract Groq rate-limit headers & token usage
        hdr_rem = resp.headers.get("x-ratelimit-remaining-tokens")
        hdr_lim = resp.headers.get("x-ratelimit-limit-tokens")
        rem_tok = int(hdr_rem) if hdr_rem and hdr_rem.isdigit() else None
        lim_tok = int(hdr_lim) if hdr_lim and hdr_lim.isdigit() else None

        usage = data.get("usage", {})
        p_tokens = usage.get("prompt_tokens", 0)
        c_tokens = usage.get("completion_tokens", 0)

        text = self._extract_text(data)
        if not p_tokens and not c_tokens:
            p_tokens = len(text) // 4 if text else 200
            c_tokens = 150

        token_tracker.record_usage(
            p_tokens, c_tokens,
            data.get("model") or payload.get("model") or self.active_model,
            rem_tok, lim_tok
        )

        if not text:
            return False, None, "Empty completion in LLM reply", status_code

        parsed = _extract_json(text)
        if parsed is None:
            return False, None, "No parseable JSON in reply", status_code

        return True, parsed, "", status_code

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        """Pulls the text out of the OpenAI-compatible response envelope."""
        try:
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        return ""

