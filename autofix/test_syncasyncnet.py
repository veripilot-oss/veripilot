"""Tests for autofix/syncasyncnet.py."""

from autofix.syncasyncnet import fix_source


def test_removes_async_posedge_reset():
    src = "always @(posedge clk or posedge reset) begin\n  if (reset) q <= 0;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[0] == "always @(posedge clk) begin"


def test_removes_async_negedge_reset_before_clock():
    # Sarang's case: reset is listed before clk in sensitivity list
    src = "always @(negedge reset or posedge clk) begin\n  if (!reset) q <= 0;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[0] == "always @(posedge clk) begin"


def test_does_not_break_multi_clock():
    # Sarang's case: dual clock block must never lose either clock
    src = "always @(posedge clk_a or posedge clk_b) begin\n  q <= d;\nend"
    new, fixed = fix_source(src, [1])
    assert new == src
    assert fixed == []


def test_removes_async_comma_reset():
    src = "always @(posedge clk, posedge rst_n) begin\n  if (!rst_n) q <= 0;\nend"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new.split("\n")[0] == "always @(posedge clk) begin"


def test_fixes_from_port_declaration_line():
    # Verilator reports SYNCASYNCNET on the port declaration line (e.g. line 2), not always line (line 4)
    src = (
        "module test(\n"
        "  input wire clk,\n"
        "  input wire reset\n"
        ");\n"
        "always @(posedge clk or posedge reset) begin\n"
        "  if (reset) q <= 0;\n"
        "end\n"
        "endmodule\n"
    )
    # Flagging line 3 (the reset port declaration) must find and fix line 5 (the always block)
    new, fixed = fix_source(src, [3])
    assert fixed == [5]
    lines = new.split("\n")
    assert lines[4] == "always @(posedge clk) begin"
    assert lines[2] == "  input wire reset"


def test_fixes_from_wire_declaration_line():
    src = (
        "module test;\n"
        "wire reset;\n"
        "always @(posedge clk or posedge reset) begin\n"
        "  if (reset) q <= 0;\n"
        "end\n"
        "endmodule\n"
    )
    new, fixed = fix_source(src, [2])
    assert fixed == [3]
    lines = new.split("\n")
    assert lines[2] == "always @(posedge clk) begin"


def test_preserves_comment_on_flagged_line():
    src = "always @(posedge clk or posedge reset) begin // async reset"
    new, fixed = fix_source(src, [1])
    assert fixed == [1]
    assert new == "always @(posedge clk) begin // async reset"


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
