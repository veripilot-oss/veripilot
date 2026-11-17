"""Tests for autofix/combdly.py."""

from autofix.combdly import fix_source


def test_changes_nonblocking_to_blocking():
    new, fixed = fix_source("always @(*) begin\n  y <= a;\nend", [2])
    assert fixed == [2]
    assert new.split("\n")[1] == "  y = a;"


def test_only_flagged_line_is_changed():
    new, fixed = fix_source("  y <= a;\n  z <= b;", [1])
    assert new == "  y = a;\n  z <= b;"
    assert fixed == [1]


def test_comparison_inside_parentheses_is_kept():
    new, _ = fix_source("  y <= (a <= b);", [1])
    assert new == "  y = (a <= b);"
    new, _ = fix_source("  if (a <= b) y <= c;", [1])
    assert new == "  if (a <= b) y = c;"


def test_comment_is_not_touched():
    new, _ = fix_source("  y <= a; // was y <= 0", [1])
    assert new == "  y = a; // was y <= 0"


def test_line_without_assignment_is_ignored():
    for line in ["  y = a;", "  if (a <= b)", "  y <<= 1;"]:
        new, fixed = fix_source(line, [1])
        assert new == line
        assert fixed == []


def test_out_of_range_line_is_ignored():
    new, fixed = fix_source("y <= a;", [9])
    assert new == "y <= a;"
    assert fixed == []
