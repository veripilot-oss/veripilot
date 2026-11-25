"""Tests for autofix/unusedsignal.py."""

from autofix.unusedsignal import fix_source


def test_unused_reg_is_removed():
    text = "module m;\n  reg [7:0] lap;\n  wire a;\nendmodule"
    new, fixed = fix_source(text, [2])
    assert fixed == [2]
    assert new == "module m;\n  wire a;\nendmodule"


def test_unused_wire_and_logic_are_removed():
    assert fix_source("  wire w;\nx", [1])[1] == [1]
    assert fix_source("  logic [3:0] l;\nx", [1])[1] == [1]


def test_port_is_never_removed():
    text = "module m(\n  input wire dbg,\n  input wire clk\n);\nendmodule"
    new, fixed = fix_source(text, [2])
    assert new == text and fixed == []


def test_signal_used_elsewhere_is_kept():
    text = "  reg [7:0] cnt;\n  always @(posedge clk) cnt <= cnt + 1;"
    new, fixed = fix_source(text, [1])
    assert new == text and fixed == []


def test_name_in_a_comment_does_not_count_as_use():
    text = "  reg lap;\n  // lap is unused\n  assign y = 1;"
    new, fixed = fix_source(text, [1])
    assert fixed == [1]


def test_longer_name_does_not_block_removal():
    text = "  reg lap;\n  reg lap2;\n  assign lap2 = 0;"
    new, fixed = fix_source(text, [1])
    assert fixed == [1]


def test_multi_name_declaration_is_skipped():
    text = "  reg a, b;\n  assign y = 1;"
    assert fix_source(text, [1])[1] == []


def test_out_of_range_line_is_ignored():
    assert fix_source("  reg a;", [9]) == ("  reg a;", [])
