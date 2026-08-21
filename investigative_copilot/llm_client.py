"""Single-provider LLM client (Groq).

Plain-HTTP implementation (``requests`` + stdlib only) so the copilot runs
without any optional SDKs installed. The provider is Groq (OpenAI-compatible
``/chat/completions``). Every call reports which provider/model served it
and its latency so the engine can expose it to the UI.

Never raises: a transport/auth failure degrades to ``(False, None, meta)``
and the caller falls back to the deterministic pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests
import threading

from backend import config

logger = logging.getLogger(__name__)

# Primary model: High-throughput 250K TPM model (never rate-limited on large prompts)
GROQ_MODEL = "openai/gpt-oss-20b"

# Fallback chain — ordered by high throughput capacity & speed
FALLBACK_MODELS = [
    "openai/gpt-oss-20b",           # Primary (250K TPM, 0.44s)
    "openai/gpt-oss-120b",          # High-capacity 120B (250K TPM, 0.48s)
    "qwen/qwen3.6-27b",             # Qwen Reasoning (8K TPM, 0.23s)
    "groq/compound-mini",           # Compound Mini (0.80s)
    "groq/compound",                # Compound Full (1.74s)
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
        self.active_model: str = GROQ_MODEL
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
            
            model = (self.active_model or GROQ_MODEL).lower()
            if "20b" in model or "120b" in model:
                base_tpm = 250000
            elif "70b" in model:
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
    """Pulls the first balanced JSON object out of an LLM reply.

    Handles markdown fences, think/thought tags, prose around the object, and
    stray leading garbage. Returns None when nothing parseable is present.
    """
    if not text:
        return None
    stripped = text.strip()
    # Strip <think>...</think> or <thought>...</thought> tags (reasoning models)
    stripped = re.sub(r"<(?:think|thought)>[\s\S]*?</(?:think|thought)>", "", stripped).strip()
    # Strip markdown code fences
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    # Fast path: the whole reply is valid JSON
    try:
        data = json.loads(stripped)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    # Bracket-matching fallback for prose-wrapped JSON
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


class LlmClient:
    """Zero-dependency HTTP client for Groq LLMs."""

    def __init__(self, active_model: str = GROQ_MODEL,
                 request_timeout: float = 45.0) -> None:
        self.active_model = os.environ.get("GROQ_MODEL", active_model)
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
            "provider": "", "model": "", "latency_ms": 0, "error": "",
        }
        keys = config.groq_keys()

        if keys:
            ok, parsed, err = self._call_groq(
                system_prompt, user_content, temperature, json_mode=True,
                keys=keys)
            meta["latency_ms"] = self.latency_ms
            if ok:
                meta["provider"] = "groq"
                meta["model"] = self.active_model
                return True, parsed, meta
            meta["error"] = f"groq: {err}"
            logger.warning("Groq call failed: %s", err)
        else:
            meta["error"] = "groq: no API key configured"
            logger.info("Groq key missing — LLM annotation disabled.")

        return False, None, meta

    def _call_groq(self, system_prompt: str, user_content: str,
                   temperature: float, json_mode: bool,
                   keys: Optional[List[str]] = None
                   ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        if not keys:
            keys = config.groq_keys()

        models_to_try = [self.active_model] + [m for m in FALLBACK_MODELS if m != self.active_model]
        last_err = "no keys configured"

        for model in models_to_try:
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

            for i, key in enumerate(keys):
                key_masked = _mask_key(key)
                logger.info(f"[Groq LLM Call] Calling model '{model}' with API Key {key_masked} (key #{i+1}/{len(keys)})...")
                print(f"[KEY] [Groq LLM Call] Calling model '{model}' with API Key {key_masked} (key #{i+1}/{len(keys)})...", flush=True)

                ok, parsed, err = self._post_json(_GROQ_URL, payload, key, self.request_timeout)
                latency_sec = self.latency_ms / 1000.0

                if ok:
                    self.active_model = model
                    logger.info(f"[Groq LLM Success] API Key {key_masked} | Model '{model}' -> SUCCEEDED in {latency_sec:.2f}s")
                    print(f"[SUCCESS] [Groq LLM Success] API Key {key_masked} | Model '{model}' -> SUCCEEDED in {latency_sec:.2f}s", flush=True)
                    return True, parsed, ""

                last_err = f"model={model} key{i}: {err}"
                logger.warning(f"[Groq LLM Error] API Key {key_masked} | Model '{model}' -> FAILED ({err})")
                print(f"[ERROR] [Groq LLM Error] API Key {key_masked} | Model '{model}' -> FAILED ({err})", flush=True)

                # Model-level errors → try next model immediately
                if any(sig in err.lower() for sig in (
                    "decommission", "not_found", "404", "model_not_found",
                    "does not exist", "unsupported"
                )):
                    curr_idx = models_to_try.index(model)
                    if curr_idx + 1 < len(models_to_try):
                        next_model = models_to_try[curr_idx + 1]
                        logger.warning(f"[Groq LLM Fallback] Model '{model}' unavailable. FALLING BACK to model '{next_model}'...")
                        print(f"[FALLBACK] [Groq LLM Fallback] Model '{model}' unavailable. FALLING BACK to model '{next_model}'...", flush=True)
                    break
                if "empty completion" in err or "no parseable json" in err.lower():
                    curr_idx = models_to_try.index(model)
                    if curr_idx + 1 < len(models_to_try):
                        next_model = models_to_try[curr_idx + 1]
                        logger.warning(f"[Groq LLM Fallback] Model '{model}' output error ({err}). FALLING BACK to model '{next_model}'...")
                        print(f"[FALLBACK] [Groq LLM Fallback] Model '{model}' output error. FALLING BACK to model '{next_model}'...", flush=True)
                    break
                # Key-level rate-limit → rotate key
                if i < len(keys) - 1:
                    next_key_masked = _mask_key(keys[i + 1])
                    logger.warning(f"[Groq LLM Key Rotation] Key {key_masked} failed. ROTATING to key #{i+2} ({next_key_masked})...")
                    print(f"[ROTATION] [Groq LLM Key Rotation] Key {key_masked} failed. ROTATING to key #{i+2} ({next_key_masked})...", flush=True)

        return False, None, last_err

    # ---------------------------------------------------------------- helpers

    def _post_json(self, url: str, payload: Dict[str, Any], key: str,
                   timeout: float
                   ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        t0 = time.monotonic()
        try:
            headers = {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
            }
            resp = requests.post(url, json=payload, timeout=timeout,
                                 headers=headers)
        except requests.RequestException as e:
            self._last_latency = int((time.monotonic() - t0) * 1000)
            return False, None, f"transport error: {type(e).__name__}"
        self._last_latency = int((time.monotonic() - t0) * 1000)
        try:
            data = resp.json()
        except ValueError:
            return False, None, f"HTTP {resp.status_code}: non-JSON reply"
        if resp.status_code != 200:
            msg = str(data.get("error", data))[:200] if isinstance(data, dict) else str(data)[:200]
            return False, None, f"HTTP {resp.status_code}: {msg}"

        # Log Groq response metadata
        choices_len = len(data.get("choices", []))
        finish_reason = (data.get("choices", [{}])[0].get("finish_reason", "unknown")
                         if choices_len > 0 else "N/A")
        message_obj = (data.get("choices", [{}])[0].get("message", {})
                       if choices_len > 0 else {})
        content_val = message_obj.get("content")
        logger.info(
            "Groq raw: model=%s status=%s choices=%s finish=%s content_len=%s",
            data.get("model", "unknown"), resp.status_code, choices_len,
            finish_reason, len(content_val) if content_val else 0,
        )

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
            return False, None, "empty completion"
        parsed = _extract_json(text)
        if parsed is None:
            return False, None, "no parseable JSON in reply"
        return True, parsed, ""

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        """Pulls the text out of the OpenAI-compatible response envelope."""
        try:
            if "choices" in data:
                return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        return ""
