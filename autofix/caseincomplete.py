"""Autofix rule for CASEINCOMPLETE: a case statement that does not cover every value.

Verilator reports the line of the `case` keyword. The fix inserts a `default:` branch just
before the matching `endcase`. A case that already has a default is left alone.

- In a clocked block (the branches use `<=`) the default is `default: ;`. The registers keep
  their value for the unlisted cases, which is what the code did before; zeroing them would
  change behavior.
- In a combinational block (the branches use `=`) the default sets every variable assigned
  in the other branches to '0, so no latch is inferred.
"""

import re

RULES = {"CASEINCOMPLETE"}
CLEARED_RULES = {"CASEINCOMPLETE"}

_TOKEN = re.compile(r"\b(case[xz]?|endcase)\b")
_ASSIGN = re.compile(r"\b([A-Za-z_]\w*)\s*(<=|(?<![=!<>])=(?![=>]))")


def _code(line):
    return line.partition("//")[0]


def _find_endcase(src, start):
    """Index of the endcase matching the case on src[start], or None."""
    depth = 0
    for idx in range(start, len(src)):
        for m in _TOKEN.finditer(_code(src[idx])):
            depth += 1 if m.group(1).startswith("case") else -1
            if depth == 0:
                return idx
    return None


def _has_own_default(body):
    """True if a default branch sits directly in this case (not in a nested one)."""
    depth = 1
    for line in body:
        code = _code(line)
        if depth == 1 and re.match(r"\s*default\b", code):
            return True
        for m in _TOKEN.finditer(code):
            depth += 1 if m.group(1).startswith("case") else -1
    return False


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix), reverse=True):  # bottom-up: inserts do not shift earlier lines
        if not 1 <= n <= len(src) or not _TOKEN.search(_code(src[n - 1])):
            continue
        end = _find_endcase(src, n - 1)
        if end is None:
            continue
        body = src[n:end]
        if _has_own_default(body):
            continue
        targets, op = [], "="
        for b in body:
            for m in _ASSIGN.finditer(_code(b)):
                if m.group(1) != "default" and m.group(1) not in targets:
                    targets.append(m.group(1))
                if m.group(2) == "<=":
                    op = "<="
        first = next((b for b in body if b.strip() and not b.strip().startswith("//")), None)
        indent = re.match(r"\s*", first).group(0) if first else re.match(r"\s*", src[end]).group(0) + "    "
        if not targets or op == "<=":
            new = [f"{indent}default: ;"]
        elif len(targets) == 1:
            new = [f"{indent}default: {targets[0]} {op} '0;"]
        else:
            new = [f"{indent}default: begin"]
            new += [f"{indent}    {t} {op} '0;" for t in targets]
            new += [f"{indent}end"]
        src[end:end] = new
        fixed.append(n)
    return "\n".join(src), sorted(fixed)
