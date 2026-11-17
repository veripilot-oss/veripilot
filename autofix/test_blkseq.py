"""Tests for autofix/blkseq.py."""

from pathlib import Path

import pytest

from autofix import core
from autofix.blkseq import fix_source, normalize_path, fix_design


def test_changes_only_the_flagged_line():
    text = "always @(posedge clk) begin\n  a = 1'b1;\n  b = 1'b1;\nend"
    new, fixed = fix_source(text, [2])
    assert fixed == [2]
    assert new.split("\n")[1] == "  a <= 1'b1;"
    assert new.split("\n")[2] == "  b = 1'b1;"


def test_only_first_plain_equals_is_changed():
    new, fixed = fix_source("  x = (a == b) ? c : d;", [1])
    assert new == "  x <= (a == b) ? c : d;"
    assert fixed == [1]


def test_leaves_comparison_and_nonblocking_alone():
    for line in ["  if (a == b)", "  q <= d;", "  if (a >= b)", "  if (a != b)"]:
        new, fixed = fix_source(line, [1])
        assert new == line
        assert fixed == []


def test_comment_is_not_touched():
    new, _ = fix_source("  a = 1; // was a = 0", [1])
    assert new == "  a <= 1; // was a = 0"


def test_out_of_range_line_is_ignored():
    new, fixed = fix_source("a = 1;", [5])
    assert new == "a = 1;"
    assert fixed == []


def test_windows_path_is_normalized():
    assert normalize_path("buggy\\fifo.v") == "buggy/fifo.v"


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.skipif(
    not core.have_verilator() or not (EXAMPLES / "fifo" / "buggy" / "fifo.v").exists(),
    reason="needs verilator and the fifo example",
)
def test_fifo_blkseq_is_fixed(tmp_path):
    design = {
        "name": "fifo",
        "findings": [
            {"rule": "BLKSEQ", "file": "fifo.v", "line": 124},
            {"rule": "BLKSEQ", "file": "buggy\\fifo.v", "line": 129},
        ],
    }
    res = fix_design(design, EXAMPLES, tmp_path)
    assert res["status"] == "kept"
    assert res["fixed_lines"] == [124, 129]
    assert "BLKSEQ" not in res["rules_after"]
    assert "BLKANDNBLK" not in res["rules_after"]
