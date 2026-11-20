"""Tests for autofix/syncasyncnet.py."""

from autofix.syncasyncnet import fix_source


def test_removes_async_posedge_reset():
    src = "always @(posedge clk or posedge reset) begin\n  if (reset) q <= 0;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[0] == "always @(posedge clk) begin"


def test_removes_async_comma_reset():
    src = "always @(posedge clk, posedge rst_n) begin\n  if (!rst_n) q <= 0;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[0] == "always @(posedge clk) begin"


def test_removes_async_negedge_reset():
    src = "always @(posedge clk or negedge reset_n) begin\n  if (!reset_n) q <= 0;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[0] == "always @(posedge clk) begin"


def test_preserves_comment_on_flagged_line():
    src = "always @(posedge clk or posedge reset) begin // async reset"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new == "always @(posedge clk) begin // async reset"


def test_only_flagged_line_is_changed():
    src = (
        "always @(posedge clk or posedge reset) begin\n"
        "always @(posedge clk or posedge reset) begin\n"
    )
    new, fixed = fix_source(src, [2])
    lines = new.split("\n")
    assert fixed == [2]
    assert "posedge reset" in lines[0]
    assert "posedge reset" not in lines[1]


def test_line_without_async_trigger_is_ignored():
    src = "always @(posedge clk) begin"
    new, fixed = fix_source(src, [1])
    assert new == src
    assert fixed == []


def test_combinational_always_is_ignored():
    src = "always @(*) begin"
    new, fixed = fix_source(src, [1])
    assert new == src
    assert fixed == []


def test_out_of_range_line_is_ignored():
    src = "always @(posedge clk or posedge reset) begin"
    new, fixed = fix_source(src, [10])
    assert new == src
    assert fixed == []
