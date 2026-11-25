"""Minimal client for the optional LLM that drafts test stimulus.

complete(prompt) returns the model's text, or None on ANY failure
(no key, network error, bad status, timeout, malformed reply). Callers
treat None as "no LLM available" and fall back to the rule-based path.

Environment:
    ANTHROPIC_API_KEY     optional; without it complete() returns None
    VERIPILOT_LLM_MODEL   optional; defaults to DEFAULT_MODEL

Standard library only. The key is never logged, printed or stored.
"""

from __future__ import annotations

import json
import os
import urllib.request
from typing import Optional

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
DEFAULT_MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 1024


def complete(prompt: str, timeout: float = 30) -> Optional[str]:
    """Send one prompt to the model and return its text, or None on failure."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        return None
    body = json.dumps({
        "model": os.environ.get("VERIPILOT_LLM_MODEL", "").strip() or DEFAULT_MODEL,
        "max_tokens": MAX_TOKENS,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    request = urllib.request.Request(
        API_URL,
        data=body,
        method="POST",
        headers={
            "x-api-key": key,
            "anthropic-version": API_VERSION,
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            reply = json.loads(response.read().decode("utf-8"))
        text = reply["content"][0]["text"]
    except Exception:
        return None
    return text if isinstance(text, str) else None
