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
import re
import time
from typing import Any, Dict, Optional, Tuple

import requests

from backend import config

logger = logging.getLogger(__name__)

GROQ_MODEL = "llama-3.3-70b-versatile"
_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"


def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    """Pulls the first balanced JSON object out of an LLM reply.

    Handles markdown fences, prose around the object, and stray leading
    garbage. Returns None when nothing parseable is present.
    """
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
        stripped = stripped.strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        pass
    start = stripped.find("{")
    if start < 0:
        return None
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(stripped[start:i + 1])
                except json.JSONDecodeError:
                    return None
    return None


class LlmClient:
    """Small stateless provider chain around ``requests``."""

    def __init__(self, groq_model: str = GROQ_MODEL,
                 groq_timeout: float = 45.0) -> None:
        self.groq_model = groq_model
        self.groq_timeout = groq_timeout
        self._last_latency = 0

    # ------------------------------------------------------------------ API

    def has_provider(self) -> bool:
        return bool(config.groq_api_keys())

    def generate_json(self, system_prompt: str, user_content: str,
                      temperature: float = 0.2,
                      json_mode: bool = True) -> Tuple[bool, Optional[Dict[str, Any]], Dict[str, Any]]:
        """Returns ``(ok, parsed_json, meta)``.

        meta: ``{"provider", "model", "latency_ms", "error"}`` — provider is
        "groq" (or "" when failed); error carries the
        human-readable failure reason for logging.
        """
        meta: Dict[str, Any] = {"provider": "", "model": "", "latency_ms": 0, "error": ""}
        keys = config.groq_api_keys()
        
        if keys:
            ok, parsed, err = self._call_groq(
                system_prompt, user_content, temperature, json_mode, keys)
            if ok:
                meta["provider"] = "groq"
                meta["model"] = self.groq_model
                meta["latency_ms"] = self._last_latency
                return True, parsed, meta
            meta["error"] = f"groq: {err}"
            logger.warning("Groq call failed: %s", err)
        else:
            meta["error"] = "groq: no API key configured"
            logger.info("Groq key missing.")

        return False, None, meta

    # ------------------------------------------------------------- providers

    def _call_groq(self, system_prompt: str, user_content: str,
                   temperature: float, json_mode: bool,
                   keys: Optional[List[str]] = None
                   ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        if not keys:
            keys = config.groq_api_keys()
        payload: Dict[str, Any] = {
            "model": self.groq_model,
            "temperature": temperature,
            "max_tokens": 4096,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
            
        last_err = "no keys configured"
        for i, key in enumerate(keys):
            ok, parsed, err = self._post_json(_GROQ_URL, payload, key,
                                              self.groq_timeout,
                                              auth_header="Authorization")
            if ok:
                return True, parsed, ""
            last_err = f"key{i}: {err}"
            if i < len(keys) - 1:
                logger.warning("Groq key %d failed (%s); rotating to next key",
                               i, err)
        return False, None, last_err

    # ---------------------------------------------------------------- helpers

    def _post_json(self, url: str, payload: Dict[str, Any], key: str,
                   timeout: float, auth_header: str = "x-goog-api-key"
                   ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        t0 = time.monotonic()
        try:
            headers = {auth_header: key}
            if auth_header == "Authorization":
                headers[auth_header] = f"Bearer {key}"
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
        text = self._extract_text(data)
        if not text:
            return False, None, "empty completion"
        parsed = _extract_json(text)
        if parsed is None:
            return False, None, "no parseable JSON in reply"
        return True, parsed, ""

    @staticmethod
    def _extract_text(data: Dict[str, Any]) -> str:
        """Pulls the text out of the provider's response envelope."""
        try:
            if "choices" in data:  # OpenAI-compatible (Groq)
                return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            pass
        return ""
