"""Autofix rule for WIDTHEXPAND: narrow sized literal assigned to a wider target.

Example: `expand_data_reg <= 8'hA5;` where target is 16 bits.
Fix: widen the literal to the target width, e.g. `16'h00A5`.
Reads the declared width of the target from the same file; if cannot be found, skip.
"""

import re
import sys
from autofix import core

RULES = {"WIDTHEXPAND"}
CLEARED_RULES = {"WIDTHEXPAND"}

_DECL = re.compile(
    r"\b(?:input|output|inout|wire|reg|logic)\s+"
    r"(?:(?:wire|reg|logic|signed|unsigned)\s+)*"
    r"(?:\[\s*([^:\]]+)\s*:\s*([^:\]]+)\s*\]\s*)?"
    r"([A-Za-z_]\w*(?:\s*,\s*[A-Za-z_]\w*)*)\s*[;,)]"
)
_PARAM = re.compile(
    r"\bparameter\s+(?:\[[^\]]+\]\s+)?([A-Za-z_]\w*)\s*=\s*([^,;)]+)"
)
# Matches assignment: target <= or = literal;
_ASSIGN = re.compile(
    r"\b([A-Za-z_]\w*)\s*(<=|(?<![=!<>])=(?![=>]))\s*(\d+)'([hHbBdDoO])([0-9a-fA-F_xXzZ]+)\s*;\s*$"
)


def _parse_params(text):
    params = {}
    for m in _PARAM.finditer(text):
        name = m.group(1)
        val_str = m.group(2).strip()
        try:
            params[name] = int(val_str, 0)
        except ValueError:
            pass
    return params


def _eval_expr(expr, params):
    expr = expr.strip()
    for k, v in params.items():
        expr = re.sub(r"\b" + k + r"\b", str(v), expr)
    try:
        val = eval(expr, {"__builtins__": None}, {})
        return int(val)
    except Exception:
        return None


def get_target_widths(text):
    """Find declared widths (in bits) for signals in the Verilog source."""
    params = _parse_params(text)
    widths = {}
    for m in _DECL.finditer(text):
        msb_str, lsb_str, names_str = m.group(1), m.group(2), m.group(3)
        if msb_str is not None and lsb_str is not None:
            msb = _eval_expr(msb_str, params)
            lsb = _eval_expr(lsb_str, params)
            if msb is not None and lsb is not None:
                w = abs(msb - lsb) + 1
            else:
                w = None
        else:
            w = 1
        for name in re.split(r"\s*,\s*", names_str.strip()):
            if name and w is not None:
                widths[name] = w
    return widths


def _widen_literal(width, base, val_digits):
    base_lower = base.lower()
    clean_digits = val_digits.replace("_", "")
    try:
        radix = {"h": 16, "d": 10, "o": 8, "b": 2}[base_lower]
        num = int(clean_digits, radix)
    except (KeyError, ValueError):
        return None

    if base_lower == "h":
        hex_digits = (width + 3) // 4
        fmt = f"{num:0{hex_digits}X}" if any(c.isupper() for c in val_digits) else f"{num:0{hex_digits}x}"
        return f"{width}'{base}{fmt}"
    elif base_lower == "b":
        return f"{width}'{base}{num:0{width}b}"
    elif base_lower == "o":
        oct_digits = (width + 2) // 3
        return f"{width}'{base}{num:0{oct_digits}o}"
    elif base_lower == "d":
        return f"{width}'{base}{num}"
    return None


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    widths = get_target_widths(text)
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        line = src[n - 1]
        code, sep, comment = line.partition("//")
        m = _ASSIGN.search(code)
        if not m:
            continue
        target, op, old_w, base, val_digits = m.group(1), m.group(2), int(m.group(3)), m.group(4), m.group(5)
        target_w = widths.get(target)
        if target_w is None or target_w <= old_w:
            continue

        widened = _widen_literal(target_w, base, val_digits)
        if widened is None:
            continue

        prefix = code[:m.start(3)]
        suffix = code[m.end(5):]
        src[n - 1] = prefix + widened + suffix + sep + comment
        fixed.append(n)
    return "\n".join(src), fixed


def fix_design(design_result, examples_dir, out_dir, require_pass=False, regress=True):
    return core.fix_design(design_result, examples_dir, out_dir, [sys.modules[__name__]],
                           regress=regress, require_pass=require_pass)


def main(argv=None):
    return core.main(argv, rules=[sys.modules[__name__]])


if __name__ == "__main__":
    sys.exit(main())
