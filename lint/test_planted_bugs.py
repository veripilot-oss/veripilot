"""Planted bugs in examples/*/bugs.yaml must be reported by Verilator on the stated line,
and the golden designs must lint clean. Expected values come from bugs.yaml, not from this file."""

import subprocess
from pathlib import Path

import pytest

from lint.linter import _get_verilator_base_cmd, lint_design, load_ground_truth

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
DESIGNS = sorted(d.name for d in EXAMPLES.iterdir() if (d / "bugs.yaml").exists())


def test_there_are_designs_to_check():
    assert DESIGNS, "no examples/*/bugs.yaml found"


@pytest.mark.parametrize("design", DESIGNS)
def test_every_planted_bug_is_reported_at_its_line(design):
    bugs = load_ground_truth(EXAMPLES / design)
    assert bugs, f"{design}/bugs.yaml lists no bugs"
    result = lint_design(design, EXAMPLES)
    by_id = {b["id"]: b for b in bugs}
    missed = [
        f"bug {i}: {by_id[i]['rule']} at {by_id[i]['file']}:{by_id[i]['line']}"
        for i in result["missed_bug_ids"]
    ]
    assert not missed, f"{design}: Verilator did not report: {missed}"
    assert result["detected"] == len(bugs)


@pytest.mark.parametrize("design", DESIGNS)
def test_golden_design_lints_clean(design):
    for rtl in sorted((EXAMPLES / design / "golden").glob("*.v")):
        res = subprocess.run(_get_verilator_base_cmd() + ["--lint-only", "-Wall", str(rtl)],
                             capture_output=True, text=True)
        output = res.stdout + res.stderr
        assert res.returncode == 0 and "%Warning" not in output and "%Error" not in output, \
            f"{rtl.name} is not lint clean:\n{output}"
