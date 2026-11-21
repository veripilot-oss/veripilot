"""Tests for autofix/latch.py."""

from autofix.latch import fix_source

BUG = "always @(*) begin\n    if (en) q = d;\nend"


def test_inserts_default_at_top_of_block():
    new, fixed = fix_source(BUG, [1])
    assert new.split("\n") == ["always @(*) begin", "    q = '0;", "    if (en) q = d;", "end"]
    assert fixed == [1]


def test_flagged_line_inside_block_finds_the_always():
    new, fixed = fix_source(BUG, [2])
    assert "    q = '0;" in new.split("\n")
    assert fixed == [2]


def test_second_run_does_not_add_a_second_default():
    once, _ = fix_source(BUG, [1])
    twice, fixed = fix_source(once, [1])
    assert twice == once
    assert fixed == []


def test_existing_default_is_not_changed():
    src = "always @(*) begin\n    q = 1'b0;\n    if (en) q = d;\nend"
    new, fixed = fix_source(src, [1])
    assert new == src and fixed == []


def test_conditional_assignment_on_its_own_line_is_not_a_default():
    src = "always @(*) begin\n    if (en)\n        q = d;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[1] == "    q = '0;"


def test_comments_are_kept_and_other_lines_untouched():
    src = "// top\nalways @(*) begin // c\n    if (en) q = d; // keep\nend\nassign z = q;"
    new, _ = fix_source(src, [2])
    lines = new.split("\n")
    assert lines[0] == "// top" and lines[1] == "always @(*) begin // c"
    assert lines[3] == "    if (en) q = d; // keep" and lines[-1] == "assign z = q;"


def test_skips_block_with_several_signals():
    src = "always @(*) begin\n    if (en) begin a = 1; b = 2; end\nend"
    assert fix_source(src, [1]) == (src, [])


def test_skips_bit_select_assignment():
    src = "always @(*) begin\n    if (en) q[0] = d;\nend"
    assert fix_source(src, [1]) == (src, [])


def test_skips_when_no_always_or_no_begin():
    for src in ["assign q = d;", "always @(*)\n    if (en) q = d;", "always @(*) begin\n    if (en) q = d;"]:
        assert fix_source(src, [1]) == (src, [])


def test_two_blocks_are_fixed_independently():
    src = BUG + "\n" + BUG.replace("q", "r")
    new, fixed = fix_source(src, [1, 4])
    assert new.count("'0;") == 2
    assert fixed == [1, 4]


def test_out_of_range_line_is_ignored():
    assert fix_source(BUG, [99]) == (BUG, [])
