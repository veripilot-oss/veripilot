"""Autofix rule for SYNCASYNCNET: net used synchronously and asynchronously as reset.

When a reset signal is used in both synchronous blocks (e.g. `always @(posedge clk)`)
and asynchronous blocks (e.g. `always @(posedge clk or posedge reset)`), Verilator
flags SYNCASYNCNET on the signal/port declaration.

Fix: Adopts a uniform synchronous reset style by changing the sensitivity list
of blocks using that signal asynchronously (e.g. `always @(posedge clk or posedge reset)`)
to synchronous `always @(posedge clk)`, removing only the edge on the named reset signal
while keeping the clock intact.
"""

from __future__ import annotations

import re

RULES = {"SYNCASYNCNET"}
CLEARED_RULES = {"SYNCASYNCNET"}

_RESET_NAME_HEURISTIC = re.compile(r"rst|reset|clear", re.IGNORECASE)


def extract_decl_signal(line: str) -> str | None:
    """Extract signal name from a port or net declaration line."""
    code = line.partition("//")[0].strip().rstrip(",;")
    m = re.search(
        r"\b(?:input|output|inout|wire|reg|logic)\b(?:\s+(?:wire|reg|logic))?(?:\s*\[[^\]]+\])?\s*(\b[a-zA-Z_]\w*\b)\s*$",
        code,
    )
    return m.group(1) if m else None


def remove_async_edge(code: str, sig: str) -> str:
    """Remove edge sensitivity on signal `sig` while preserving clocks and formatting."""
    pat1 = re.compile(rf"""(?:,\s*|\s+or\s+)(?:posedge|negedge)\s+\b{re.escape(sig)}\b""", re.IGNORECASE)
    pat2 = re.compile(rf"""(\(\s*)(?:posedge|negedge)\s+\b{re.escape(sig)}\b\s+(?:or\s+|,)\s*""", re.IGNORECASE)
    new_code = pat1.sub("", code)
    new_code = pat2.sub(r"\1", new_code)
    return new_code


def fix_line(code: str, sig: str | None = None) -> str:
    """Make the sensitivity list of an always block purely synchronous."""
    if not re.search(r"\balways\s*@", code):
        return code

    if not re.search(r"\bposedge\b|\bnegedge\b", code):
        return code

    if sig:
        return remove_async_edge(code, sig)

    # If no specific signal was named, only remove edges on signals matching reset heuristic
    edges = re.findall(r"(?:posedge|negedge)\s+([a-zA-Z_]\w*)", code, re.IGNORECASE)
    reset_sigs = [s for s in edges if _RESET_NAME_HEURISTIC.search(s)]
    new_code = code
    for r_sig in reset_sigs:
        new_code = remove_async_edge(new_code, r_sig)
    return new_code


def fix_source(text: str, lines_to_fix: list[int]) -> tuple[str, list[int]]:
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers.

    Verilator reports SYNCASYNCNET on the port/net declaration line of the
    reset signal, not on the always block. If a declaration line is flagged,
    we extract the signal name and make any always blocks using it asynchronously
    synchronous. If an always line is directly flagged, we fix that line.
    """
    src = text.split("\n")
    fixed_lines: set[int] = set()

    target_signals: set[str] = set()
    always_lines: set[int] = set()

    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        line = src[n - 1]
        sig = extract_decl_signal(line)
        if sig:
            target_signals.add(sig)
        elif re.search(r"\balways\s*@", line):
            always_lines.add(n)

    # 1. If declaration lines were flagged, find and fix matching always blocks
    if target_signals:
        for idx, line in enumerate(src):
            if re.search(r"\balways\s*@", line):
                code, sep, comment = line.partition("//")
                new_code = code
                for sig in target_signals:
                    if re.search(rf"\b(?:posedge|negedge)\s+{re.escape(sig)}\b", new_code):
                        new_code = remove_async_edge(new_code, sig)
                if new_code != code:
                    src[idx] = new_code + sep + comment
                    fixed_lines.add(idx + 1)

    # 2. If always lines were directly flagged
    for n in always_lines:
        line = src[n - 1]
        code, sep, comment = line.partition("//")
        new_code = fix_line(code)
        if new_code != code:
            src[n - 1] = new_code + sep + comment
            fixed_lines.add(n)

    return "\n".join(src), sorted(fixed_lines)
