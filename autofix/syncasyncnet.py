"""Autofix rule for SYNCASYNCNET: net used synchronously and asynchronously as reset.

When a reset signal is used in both synchronous blocks (e.g. `always @(posedge clk)`)
and asynchronous blocks (e.g. `always @(posedge clk or posedge reset)`), Verilator
flags SYNCASYNCNET.

Fix: Adopts a uniform synchronous reset style by changing the sensitivity list
`always @(posedge clk or posedge <signal>)` to `always @(posedge clk)` on the flagged line.
"""

import re

RULES = {"SYNCASYNCNET"}
CLEARED_RULES = {"SYNCASYNCNET"}

# Pattern matching asynchronous edge triggers on reset in sensitivity list:
# e.g., 'always @(posedge clk or posedge reset)' -> 'always @(posedge clk)'
# or 'always @(posedge clk, posedge reset)'
# or 'always @(negedge reset or posedge clk)' -> 'always @(posedge clk)'
_ASYNC_RESET_PATTERNS = [
    # ', posedge rst' or ' or posedge rst' or ' or negedge rst'
    (re.compile(r"""\s*(?:,\s*|\s+or\s+)(?:posedge|negedge)\s+\w+""", re.IGNORECASE), ""),
    # '(posedge rst or ' or '(negedge rst or ' at start of sensitivity list
    (re.compile(r"""(\(\s*)(?:posedge|negedge)\s+\w+\s+(?:or|,)\s*""", re.IGNORECASE), r"\1"),
]


def fix_line(code: str) -> str:
    """Make the sensitivity list of an always block purely synchronous."""
    # Match always @(...)
    if not re.search(r"\balways\s*@", code):
        return code

    # Only modify if both clk and an async edge trigger are present
    if not re.search(r"\bposedge\b|\bnegedge\b", code):
        return code

    new_code = code
    for pat, repl in _ASYNC_RESET_PATTERNS:
        new_code = pat.sub(repl, new_code)
    return new_code


def fix_source(text: str, lines_to_fix: list[int]) -> tuple[str, list[int]]:
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        line = src[n - 1]
        code, sep, comment = line.partition("//")
        new_code = fix_line(code)
        if new_code != code:
            src[n - 1] = new_code + sep + comment
            fixed.append(n)
    return "\n".join(src), fixed
