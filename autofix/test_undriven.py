"""Tests for autofix/undriven.py."""

from autofix.undriven import fix_source


def test_internal_wire_is_tied_to_zero():
    new, fixed = fix_source("  wire par;", [1])
    assert fixed == [1]
    assert new == "  wire par = 1'b0;"


def test_ranged_wire_gets_sized_zero():
    new, _ = fix_source("  wire [7:0] bus;", [1])
    assert new == "  wire [7:0] bus = 8'b0;"


def test_output_port_gets_assign_after_port_list():
    text = "module m(\n  input wire clk,\n  output wire st\n);\n  reg x;\nendmodule"
    new, fixed = fix_source(text, [3])
    assert fixed == [3]
    assert new.split("\n")[3:5] == [");", "    assign st = 1'b0;"]


def test_output_port_with_range():
    text = "module m(\n  output wire [3:0] st\n);\nendmodule"
    new, _ = fix_source(text, [2])
    assert "assign st = 4'b0;" in new


def test_reg_and_output_reg_are_skipped():
    assert fix_source("  reg x;", [1])[1] == []
    assert fix_source("module m(\n  output reg q\n);", [2])[1] == []


def test_two_fixes_in_one_file_keep_their_lines():
    text = "module m(\n  output wire a\n);\n  wire b;\nendmodule"
    new, fixed = fix_source(text, [2, 4])
    assert fixed == [2, 4]
    assert "  wire b = 1'b0;" in new and "    assign a = 1'b0;" in new


def test_comment_is_kept():
    new, _ = fix_source("  wire par; // parity", [1])
    assert new == "  wire par = 1'b0; // parity"


def test_other_lines_are_ignored():
    assert fix_source("  assign y = a;", [1]) == ("  assign y = a;", [])
