"""Autofix rule for UNUSEDSIGNAL: an internal reg/wire/logic that is declared but never used.

The fix deletes the declaration line. It is deliberately narrow:

- Only a one-name `reg`/`wire`/`logic` declaration on its own line is removed.
- A port (`input`/`output`/`inout`) is never removed: that would break every instance and
  testbench that connects it, so those lines are skipped.
- If the name appears anywhere else in the file, the line is skipped. Verilator also flags
  signals that are only partly used, and deleting those would break the design.
"""

import re

RULES = {"UNUSEDSIGNAL"}
CLEARED_RULES = {"UNUSEDSIGNAL"}
PARTIAL = True  # ports and partly used signals stay flagged

_DECL = re.compile(
    r"^\s*(?:reg|wire|logic)\b(?:\s+signed)?(?:\s*\[[^\]]*\])*\s*([A-Za-z_]\w*)\s*(?:\[[^\]]*\]\s*)*;\s*$"
)


def _code(line):
    return line.partition("//")[0]


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        m = _DECL.match(_code(src[n - 1]))
        if not m:
            continue
        name = m.group(1)
        word = re.compile(r"\b" + re.escape(name) + r"\b")
        others = [_code(s) for i, s in enumerate(src) if i != n - 1 and s is not None]
        if any(word.search(s) for s in others):
            continue
        src[n - 1] = None
        fixed.append(n)
    return "\n".join(s for s in src if s is not None), fixed
