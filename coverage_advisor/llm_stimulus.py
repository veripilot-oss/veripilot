"""LLM-based stimulus generator for VeriPilot coverage advisor.

Wraps llm_client.complete() to draft Verilog test stimulus targeting
uncovered RTL lines.  Returns None on any failure so callers can fall
back to rule-based generation gracefully.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Safety constants
# ---------------------------------------------------------------------------

_BLOCKED_TOKENS = (
    "$system",
    "$fopen",
    "$fwrite",
    "$fdisplay",
    "$readmem",
    "`include",
    "$value$plusargs",
)
_MAX_LINES = 200

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _strip_markdown_fences(text: str) -> str:
    """Remove leading/trailing markdown code fences if present."""
    lines = text.splitlines()
    if lines and re.match(r"^```", lines[0].strip()):
        lines = lines[1:]
    if lines and re.match(r"^```", lines[-1].strip()):
        lines = lines[:-1]
    return "\n".join(lines)


def _is_safe(snippet: str) -> bool:
    """Return False if the snippet contains dangerous system calls or is too long."""
    for token in _BLOCKED_TOKENS:
        if token in snippet:
            return False
    if len(snippet.splitlines()) > _MAX_LINES:
        return False
    return True


def _build_prompt(design_name: str, context: str, golden_src: str) -> str:
    return (
        f"You are a Verilog testbench engineer.\n"
        f"Design: {design_name}\n\n"
        f"The following RTL lines are NOT yet covered by the existing testbench:\n"
        f"{context}\n\n"
        f"Golden RTL source ({design_name}.v):\n"
        f"{golden_src}\n\n"
        "Return ONLY a Verilog stimulus snippet (no markdown fences, no explanation) "
        "that exercises the uncovered lines above. "
        "Use only synthesisable Verilog constructs: clocked @(posedge/negedge clk) blocks, "
        "signal assignments, repeat/begin/end. "
        "Do NOT use $system, $fopen, $fwrite, $fdisplay to files, $readmem, `include, "
        "or $value$plusargs. Keep the snippet under 200 lines."
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate(design_name: str, uncovered_items: list[dict[str, Any]]) -> str | None:
    """Draft Verilog test stimulus using an LLM for uncovered RTL lines.

    Parameters
    ----------
    design_name:
        Name of the RTL design (e.g. "fifo", "spi", "timer").
    uncovered_items:
        List of dicts with at least "line" and "code" keys, as returned by
        coverage_advisor.advisor.run_design_coverage.

    Returns
    -------
    str | None
        A Verilog stimulus snippet, or None if the LLM is unavailable,
        returns an unsafe response, or any other error occurs.
    """
    # Import lazily so a missing llm_client does not break the module.
    try:
        from coverage_advisor import llm_client  # type: ignore[import]
    except ImportError:
        return None

    if not uncovered_items:
        return None

    # Build context from uncovered items using the same helper as the rule-based path.
    try:
        from coverage_advisor.stimulus_advisor import extract_uncovered_context
        context = extract_uncovered_context(uncovered_items)
    except Exception:
        return None

    # Read the golden RTL source for the design.
    golden_path = Path(f"examples/{design_name}/golden/{design_name}.v")
    if not golden_path.exists():
        # Try relative to repo root resolved from this file's location.
        repo_root = Path(__file__).resolve().parent.parent
        golden_path = repo_root / "examples" / design_name / "golden" / f"{design_name}.v"
    if not golden_path.exists():
        return None

    try:
        golden_src = golden_path.read_text(encoding="utf-8")
    except OSError:
        return None

    prompt = _build_prompt(design_name, context, golden_src)

    # Call the LLM client.
    try:
        raw = llm_client.complete(prompt)
    except Exception:
        return None

    if raw is None:
        return None

    snippet = _strip_markdown_fences(raw).strip()
    if not snippet:
        return None

    if not _is_safe(snippet):
        return None

    return snippet
