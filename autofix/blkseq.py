"""Autofix rule for BLKSEQ: blocking assignment '=' inside a clocked always block.

Changes the first plain '=' on each flagged line to '<='. BLKANDNBLK is reported on the
register declaration and disappears once every blocking assignment to that register is
fixed, so it is not edited separately (it is listed in CLEARED_RULES).

The shared apply / re-lint / keep-or-revert loop lives in autofix/core.py.
"""

import re
import sys

from autofix import core
from autofix.core import normalize_path  # noqa: F401  (kept for existing callers)

RULES = {"BLKSEQ"}
CLEARED_RULES = {"BLKSEQ", "BLKANDNBLK"}
# first '=' that is not part of ==, !=, <=, >=, =>
ASSIGN = re.compile(r"(?<![=!<>])=(?![=>])")


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        line = src[n - 1]
        code, sep, comment = line.partition("//")
        new_code, count = ASSIGN.subn("<=", code, count=1)
        if count:
            src[n - 1] = new_code + sep + comment
            fixed.append(n)
    return "\n".join(src), fixed


def fix_design(design_result, examples_dir, out_dir, require_pass=False, regress=True):
    """Apply only this rule to one design (see core.fix_design)."""
    return core.fix_design(design_result, examples_dir, out_dir, [sys.modules[__name__]],
                           regress=regress, require_pass=require_pass)


def main(argv=None):
    return core.main(argv, rules=[sys.modules[__name__]])


if __name__ == "__main__":
    sys.exit(main())
