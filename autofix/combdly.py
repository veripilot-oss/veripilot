"""Autofix rule for COMBDLY: non-blocking '<=' inside a combinational always block.

Changes the assignment '<=' on each flagged line to '='. Only a '<=' outside any
parentheses, brackets or braces is touched, so a comparison such as `x <= (a <= b)` or
`if (a <= b) x <= 1;` keeps its comparison operator.
"""

RULES = {"COMBDLY"}
CLEARED_RULES = {"COMBDLY"}

_OPEN, _CLOSE = "([{", ")]}"


def _assign_index(code):
    """Index of the first top-level '<=' that is an assignment, or None."""
    depth = 0
    for i, ch in enumerate(code):
        if ch in _OPEN:
            depth += 1
        elif ch in _CLOSE:
            depth -= 1
        elif depth == 0 and code.startswith("<=", i):
            prev = code[i - 1] if i else ""
            nxt = code[i + 2] if i + 2 < len(code) else ""
            if prev != "<" and nxt != "=":  # not '<<=' and not '<=='
                return i
    return None


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        code, sep, comment = src[n - 1].partition("//")
        i = _assign_index(code)
        if i is not None:
            src[n - 1] = code[:i] + "=" + code[i + 2:] + sep + comment
            fixed.append(n)
    return "\n".join(src), fixed
