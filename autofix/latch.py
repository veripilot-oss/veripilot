"""Autofix rule for LATCH: a combinational always block that does not assign a signal on every path.

Verilator reports the `always @(*) begin` line. The fix inserts a default `<signal> = '0;` as
the first statement of that block, so the signal has a value on every path and no latch is
inferred. The flagged line may also be a line inside the block: the rule scans upwards for the
enclosing `always @(*) begin`.

The warning's signal name is not passed to a rule, so it is read from the block. The rule is
conservative and skips the block when:
- no enclosing `always @(*) begin` is found, or the block has no matching `end`;
- the block assigns more than one signal (it cannot tell which one latches);
- the signal is assigned with a bit or part select (a default would need the full width);
- the signal already has an unconditional assignment at the top level of the block.
"""

import re

RULES = {"LATCH"}
CLEARED_RULES = {"LATCH"}

_ALWAYS = re.compile(r"^\s*always\s*@\s*(\(\s*\*\s*\)|\*)\s*begin\b")
_TOKEN = re.compile(r"\b(begin|end)\b")
_ASSIGN = re.compile(r"^\s*([A-Za-z_]\w*)\s*(\[[^\]]*\]\s*)?(<=|=)(?![=>])")
_ASSIGN_ANY = re.compile(r"(?<![\w$.])([A-Za-z_]\w*)\s*(\[[^\]]*\]\s*)?(<=|(?<![=!<>])=(?![=>]))")
_KEYWORDS = {"if", "else", "case", "casez", "casex", "begin", "end", "for", "while"}


def _code(line):
    return line.partition("//")[0]


def _find_always(src, n):
    """Index of the `always @(*) begin` at or above line index n, or None."""
    for i in range(n, -1, -1):
        code = _code(src[i])
        if _ALWAYS.match(code):
            return i
        if re.search(r"\bendmodule\b", code):
            return None
    return None


def _find_end(src, start):
    depth = 0
    for i in range(start, len(src)):
        for m in _TOKEN.finditer(_code(src[i])):
            depth += 1 if m.group(1) == "begin" else -1
            if depth == 0:
                return i
    return None


def _assigned(body):
    """Names assigned in the block, and whether any assignment uses a select."""
    names, selected = set(), False
    for line in body:
        for m in _ASSIGN_ANY.finditer(_code(line)):
            if m.group(1) in _KEYWORDS:
                continue
            names.add(m.group(1))
            selected = selected or bool(m.group(2))
    return names, selected


def _has_default(body, sig):
    """True if sig is assigned unconditionally at the top level of the block."""
    depth, prev = 1, "begin"
    for line in body:
        code = _code(line).strip()
        if not code:
            continue
        m = _ASSIGN.match(code)
        if depth == 1 and m and m.group(1) == sig and not m.group(2) and (
                prev.endswith(";") or prev == "begin" or prev == "end"):
            return True
        for t in _TOKEN.finditer(code):
            depth += 1 if t.group(1) == "begin" else -1
        prev = code
    return False


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed, done = [], set()
    for n in sorted(set(lines_to_fix), reverse=True):  # bottom-up: inserts do not shift earlier lines
        if not 1 <= n <= len(src):
            continue
        start = _find_always(src, n - 1)
        if start is None or start in done:
            continue
        end = _find_end(src, start)
        if end is None:
            continue
        body = src[start + 1:end]
        names, selected = _assigned(body)
        if len(names) != 1 or selected:
            continue
        sig = next(iter(names))
        if _has_default(body, sig):
            continue
        indent = re.match(r"\s*", src[start]).group(0) + "    "
        src.insert(start + 1, f"{indent}{sig} = '0;")
        done.add(start)
        fixed.append(n)  # the flagged line, as the other rules report it
    return "\n".join(src), sorted(fixed)
