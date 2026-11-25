"""Autofix rule for UNDRIVEN: a net or output port that is declared but never driven.

The fix ties the signal to zero:

- `wire [N:0] x;` becomes `wire [N:0] x = <zero>;` (an internal wire).
- `output wire x` (a port) gets `assign x = <zero>;` inserted after the `);` that closes
  the module's port list.

The zero is sized from a numeric range such as `[7:0]`; with no range it is `1'b0`, and with
a non-numeric range it is `'0`. A `reg`, an `output reg`, or a declaration with several
names is skipped, because tying those off needs a procedural block or a bigger rewrite.
"""

import re

RULES = {"UNDRIVEN"}
CLEARED_RULES = {"UNDRIVEN"}
PARTIAL = True  # ports and partly used signals stay flagged

_WIRE = re.compile(r"^(\s*wire\b)((?:\s+signed)?)((?:\s*\[[^\]]*\])?)\s*([A-Za-z_]\w*)\s*;\s*$")
_PORT = re.compile(r"^\s*output\s+(?:wire\s+)?(?:signed\s+)?((?:\[[^\]]*\]\s*)?)([A-Za-z_]\w*)\s*,?\s*$")
_RANGE = re.compile(r"\[\s*(\d+)\s*:\s*(\d+)\s*\]")


def _split(line):
    code, sep, comment = line.partition("//")
    return code, sep + comment


def _zero(rng):
    if not rng.strip():
        return "1'b0"
    m = _RANGE.fullmatch(rng.strip())
    if m:
        return f"{abs(int(m.group(1)) - int(m.group(2))) + 1}'b0"
    return "'0"


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    inserts = []  # (index to insert after, new line)
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        code, comment = _split(src[n - 1])
        m = _WIRE.match(code)
        if m:
            head, signed, rng, name = m.groups()
            src[n - 1] = f"{head}{signed}{(' ' + rng.strip()) if rng.strip() else ''} {name} = {_zero(rng)};" + (
                " " + comment if comment else "")
            fixed.append(n)
            continue
        m = _PORT.match(code)
        if m:
            rng, name = m.groups()
            for j in range(n - 1, len(src)):
                if _split(src[j])[0].strip().startswith(")"):
                    inserts.append((j, f"    assign {name} = {_zero(rng)};"))
                    fixed.append(n)
                    break
    for j, line in sorted(inserts, reverse=True):
        src.insert(j + 1, line)
    return "\n".join(src), fixed
