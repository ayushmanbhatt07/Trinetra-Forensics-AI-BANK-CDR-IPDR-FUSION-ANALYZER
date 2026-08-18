"""Single-provider LLM client (OpenRouter).

Plain-HTTP implementation (``requests`` + stdlib only) so the copilot runs
without any optional SDKs installed. The provider is OpenRouter (OpenAI-compatible
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
from typing import Any, Dict, Optional, Tuple

import requests

from backend import config

logger = logging.getLogger(__name__)

OPENROUTER_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
FALLBACK_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "z-ai/glm-5.2:free",
    "nvidia/nemotron-3.5-lightning:free",
    "nvidia/nemotron-3-super-120b-a12b:free",
]
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


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
    in_str = False
    esc = False
    for i in range(start, len(stripped)):
        ch = stripped[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(stripped[start:i + 1])
                    if isinstance(obj, dict):
                        return obj
                except Exception:
                    pass
                return None
    return None


class LlmClient:
    """Zero-dependency HTTP client for OpenRouter LLMs."""

    def __init__(self, active_model: str = OPENROUTER_MODEL,
                 request_timeout: float = 45.0) -> None:
        self.active_model = os.environ.get("OPENROUTER_MODEL", active_model)
        self.request_timeout = request_timeout
        self._last_latency = 0

    @property
    def latency_ms(self) -> int:
        return self._last_latency

    def has_provider(self) -> bool:
        """True when at least one OpenRouter API key is configured."""
        return bool(config.open_router_keys())

    def generate_json(self, system_prompt: str, user_content: str,
                      temperature: float = 0.1
                      ) -> Tuple[bool, Optional[Dict[str, Any]], Dict[str, Any]]:
        meta: Dict[str, Any] = {
            "provider": "", "model": "", "latency_ms": 0, "error": "",
        }
        keys = config.open_router_keys()

        if keys:
            ok, parsed, err = self._call_openrouter(
                system_prompt, user_content, temperature, json_mode=True,
                keys=keys)
            meta["latency_ms"] = self.latency_ms
            if ok:
                meta["provider"] = "openrouter"
                meta["model"] = self.active_model
                return True, parsed, meta
            meta["error"] = f"openrouter: {err}"
            logger.warning("OpenRouter call failed: %s", err)
        else:
            meta["error"] = "openrouter: no API key configured"
            logger.info("OpenRouter key missing.")

        return False, None, meta

    def _call_openrouter(self, system_prompt: str, user_content: str,
                         temperature: float, json_mode: bool,
                         keys: Optional[List[str]] = None
                         ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        if not keys:
            keys = config.open_router_keys()

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
                ok, parsed, err = self._post_json(_OPENROUTER_URL, payload, key,
                                                  self.request_timeout,
                                                  auth_header="Authorization")
                if ok:
                    self.active_model = model
                    return True, parsed, ""
                last_err = f"model={model} key{i}: {err}"
                if "decommission" in err.lower() or "not_found" in err.lower() or "404" in err:
                    logger.warning(f"OpenRouter model {model} unavailable, trying fallback model...")
                    break
                if "empty completion" in err or "no parseable json" in err.lower():
                    logger.warning(f"OpenRouter model {model} failed to generate valid response ({err}), trying fallback model...")
                    break
                if i < len(keys) - 1:
                    logger.warning("OpenRouter key %d failed (%s); rotating to next key", i, err)

        return False, None, last_err

    # ---------------------------------------------------------------- helpers

    def _post_json(self, url: str, payload: Dict[str, Any], key: str,
                   timeout: float, auth_header: str = "x-goog-api-key"
                   ) -> Tuple[bool, Optional[Dict[str, Any]], str]:
        t0 = time.monotonic()
        try:
            headers = {
                auth_header: key,
                "HTTP-Referer": "http://localhost:8000",
                "X-Title": "Trinetra Investigative Copilot",
            }
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
            
        # Log OpenRouter metadata
        choices_len = len(data.get("choices", []))
        finish_reason = data.get("choices", [{}])[0].get("finish_reason", "unknown") if choices_len > 0 else "N/A"
        message_obj = data.get("choices", [{}])[0].get("message", {}) if choices_len > 0 else {}
        content_val = message_obj.get("content")
        logger.info(f"OpenRouter Raw: model={data.get('model', 'unknown')} status={resp.status_code} "
                    f"choices={choices_len} finish_reason={finish_reason} "
                    f"content_present={'yes' if content_val else 'no'} content_length={len(content_val) if content_val else 0}")
                    
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
