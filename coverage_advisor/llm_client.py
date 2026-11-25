"""Minimal client for the optional LLM that drafts test stimulus.

complete(prompt) returns the model's text, or None on ANY failure
(no key, empty prompt, network error, bad status, timeout, malformed
reply). Callers treat None as "no LLM available" and fall back to the
rule-based path.

Works with any OpenAI-compatible chat-completions endpoint, so a free
tier (Groq, Google Gemini, OpenRouter free models) or a local Ollama
server can be used. Environment:

    VERIPILOT_LLM_API_KEY    key for the endpoint; without it complete()
                             returns None, unless the base URL is local
    VERIPILOT_LLM_BASE_URL   default DEFAULT_BASE_URL (Groq free tier);
                             e.g. http://localhost:11434/v1 for Ollama
    VERIPILOT_LLM_MODEL      default DEFAULT_MODEL; model ids change, so
                             set this if the default is not available

Standard library only. The key is never logged, printed or stored.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

DEFAULT_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_TOKENS = 1024
_LOCAL_PREFIXES = ("http://localhost", "http://127.0.0.1")


def _text_of(reply) -> Optional[str]:
    """First text answer in a chat-completions reply, or None."""
    content = reply["choices"][0]["message"]["content"]
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                return part["text"]
    return None


def complete(prompt: str, timeout: float = 30) -> Optional[str]:
    """Send one prompt to the model and return its text, or None on failure."""
    if not isinstance(prompt, str) or not prompt.strip():
        return None
    base = os.environ.get("VERIPILOT_LLM_BASE_URL", "").strip().rstrip("/") or DEFAULT_BASE_URL
    key = os.environ.get("VERIPILOT_LLM_API_KEY", "").strip()
    if not key and not base.startswith(_LOCAL_PREFIXES):
        return None
    headers = {"content-type": "application/json", "user-agent": "veripilot-llm-client"}
    if key:
        headers["authorization"] = "Bearer " + key
    body = json.dumps({
        "model": os.environ.get("VERIPILOT_LLM_MODEL", "").strip() or DEFAULT_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    request = urllib.request.Request(base + "/chat/completions", data=body, method="POST", headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return _text_of(json.loads(response.read().decode("utf-8")))
    except Exception:
        return None
