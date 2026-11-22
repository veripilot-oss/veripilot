"""Autofix rule for PINMISSING: a submodule instance omits a port connection.

Adds the missing named connection(s) to the instance:
- output port: `/* verilator lint_off PINCONNECTEMPTY */ .<port>() /* verilator lint_on PINCONNECTEMPTY */`
  (left unconnected on purpose, without raising PINCONNECTEMPTY)
- input port: a sized zero, `.<port>(1'b0)` / `.<port>(16'b0)` (`'0` when the width is a parameter)

Port directions come from the submodule's ANSI port list in the same file. The instance is
skipped when the module is not found (or is defined twice), when a missing port is an inout or
has no direction, or when the instance uses positional or `.*` connections.

The new text is appended to the last connection line, so the line count never changes and
only that line is returned as fixed.
"""

import re

RULES = {"PINMISSING"}
CLEARED_RULES = {"PINMISSING"}

_IDENT = r"[A-Za-z_][A-Za-z0-9_$]*"
_MODULE_HEAD = re.compile(
    rf"\bmodule\s+({_IDENT})\s*(?:#\s*\((?:[^()]|\([^()]*\))*\)\s*)?\((.*?)\)\s*;", re.S)
_PORT_DECL = re.compile(
    rf"\b(input|output|inout)\b\s*(?:wire|reg|logic)?\s*(?:signed\s*)?(?:\[([^\]]+)\])?\s*({_IDENT})")
_INST_START = re.compile(rf"^\s*({_IDENT})\s*(?:#\s*\(.*?\)\s*)?({_IDENT})\s*\(")
_KEYWORDS = {"module", "if", "for", "while", "case", "assign", "always", "initial", "function",
             "task", "begin", "end", "else", "wire", "reg", "input", "output", "inout"}


def _strip_comments(text):
    """Blank out comments, keeping length and newlines so offsets still line up."""
    def blank(m):
        return re.sub(r"[^\n]", " ", m.group(0))
    return re.sub(r"//[^\n]*|/\*.*?\*/", blank, text, flags=re.S)


def _parse_modules(code):
    """module name -> {port: (direction, width)}; a module defined twice maps to None."""
    modules = {}
    for m in _MODULE_HEAD.finditer(code):
        name = m.group(1)
        if name in modules:
            modules[name] = None
            continue
        ports = {}
        for p in _PORT_DECL.finditer(m.group(2)):
            ports[p.group(3)] = (p.group(1), p.group(2).strip() if p.group(2) else None)
        modules[name] = ports or None
    return modules


def _zero(width):
    if not width:
        return "1'b0"
    m = re.fullmatch(r"\s*(\d+)\s*:\s*(\d+)\s*", width)
    if m:
        return f"{abs(int(m.group(1)) - int(m.group(2))) + 1}'b0"
    return "'0"


def _find_instance(code_lines, flagged):
    """Return (start_idx, module_name) of the instance covering 0-based line `flagged`."""
    for i in range(flagged, max(-1, flagged - 50), -1):
        m = _INST_START.match(code_lines[i])
        if m and m.group(1) not in _KEYWORDS:
            return i, m.group(1)
        if i != flagged and (";" in code_lines[i] or "endmodule" in code_lines[i]):
            break
    return None, None


def _find_close(code_lines, start, open_col):
    """Return (line_idx, col) of the `)` that closes the port list opened at open_col."""
    depth = 0
    for i in range(start, len(code_lines)):
        line = code_lines[i]
        for j in range(open_col if i == start else 0, len(line)):
            if line[j] == "(":
                depth += 1
            elif line[j] == ")":
                depth -= 1
                if depth == 0:
                    return i, j
    return None, None


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    lines = text.split("\n")
    code_lines = _strip_comments(text).split("\n")
    modules = _parse_modules("\n".join(code_lines))
    fixed = set()
    done = set()

    for flagged in sorted(set(lines_to_fix)):
        if not 1 <= flagged <= len(lines):
            continue
        start, mod = _find_instance(code_lines, flagged - 1)
        if start is None or start in done or not modules.get(mod):
            continue
        open_col = _INST_START.match(code_lines[start]).end() - 1
        end, col = _find_close(code_lines, start, open_col)
        if end is None:
            continue
        done.add(start)

        # (line, lo, hi) spans of the port list body
        spans = [(i, open_col + 1 if i == start else 0, col if i == end else len(code_lines[i]))
                 for i in range(start, end + 1)]
        body = "\n".join(code_lines[i][lo:hi] for i, lo, hi in spans)
        if ".*" in body:
            continue
        connected = set(re.findall(rf"\.\s*({_IDENT})\s*\(", body))
        if body.strip() and not connected:
            continue  # positional connections

        ports = modules[mod]
        missing = [p for p in ports if p not in connected]
        if not missing:
            continue
        conns = []
        for p in missing:
            direction, width = ports[p]
            if direction == "output":
                conns.append(f"/* verilator lint_off PINCONNECTEMPTY */ .{p}() "
                             f"/* verilator lint_on PINCONNECTEMPTY */")
            elif direction == "input":
                conns.append(f".{p}({_zero(width)})")
            else:
                conns = None
                break
        if not conns:
            continue

        # Insert right after the last code character inside the port list.
        target, pos, sep = start, open_col + 1, ""
        for i, lo, hi in reversed(spans):
            seg = code_lines[i][lo:hi].rstrip()
            if seg.strip():
                target, pos = i, lo + len(seg)
                sep = " " if seg.endswith(",") else ", "
                break
        lines[target] = lines[target][:pos] + sep + ", ".join(conns) + lines[target][pos:]
        fixed.add(target + 1)

    return "\n".join(lines), sorted(fixed)
