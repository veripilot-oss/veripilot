"""Autofix rule for WIDTHTRUNC: a wider value assigned to a narrower reg.

Example: `trunc_ptr_reg <= write;` where target is 4 bits and write is 5 bits.
Fix: slice the right-hand side to the target width, e.g. `write[3:0]`.
Condition: apply only when the right-hand side is a plain identifier and the target width is known.
"""

import re
import sys
from autofix import core
from autofix.widthexpand import get_target_widths

RULES = {"WIDTHTRUNC"}
CLEARED_RULES = {"WIDTHTRUNC"}

# Matches assignment: target <= or = plain_rhs_identifier;
_ASSIGN_PLAIN_ID = re.compile(
    r"\b([A-Za-z_]\w*)\s*(<=|(?<![=!<>])=(?![=>]))\s*([A-Za-z_]\w*)\s*;\s*$"
)


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
        m = _ASSIGN_PLAIN_ID.search(code)
        if not m:
            continue
        target, op, rhs_id = m.group(1), m.group(2), m.group(3)
        target_w = widths.get(target)
        if target_w is None or target_w <= 0:
            continue

        slice_str = f"{rhs_id}[{target_w - 1}:0]"
        prefix = code[:m.start(3)]
        suffix = code[m.end(3):]
        src[n - 1] = prefix + slice_str + suffix + sep + comment
        fixed.append(n)
    return "\n".join(src), fixed


def fix_design(design_result, examples_dir, out_dir, require_pass=False, regress=True):
    return core.fix_design(design_result, examples_dir, out_dir, [sys.modules[__name__]],
                           regress=regress, require_pass=require_pass)


def main(argv=None):
    return core.main(argv, rules=[sys.modules[__name__]])


if __name__ == "__main__":
    sys.exit(main())
