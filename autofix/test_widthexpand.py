"""Tests for autofix/widthexpand.py."""

from autofix.widthexpand import fix_source


def test_widens_hex_literal():
    code = (
        "module m;\n"
        "  reg [15:0] expand_data_reg;\n"
        "  always @(posedge clk) begin\n"
        "    expand_data_reg <= 8'hA5;\n"
        "  end\n"
        "endmodule"
    )
    new, fixed = fix_source(code, [4])
    assert fixed == [4]
    assert "expand_data_reg <= 16'h00A5;" in new


def test_widens_with_parameter_width():
    code = (
        "module m #(\n"
        "  parameter WORD_WIDTH = 16\n"
        ") ();\n"
        "  reg [WORD_WIDTH - 1:0] expand_data_reg;\n"
        "  always @(posedge clk) begin\n"
        "    expand_data_reg <= 8'hA5; // comment\n"
        "  end\n"
        "endmodule"
    )
    new, fixed = fix_source(code, [6])
    assert fixed == [6]
    assert "expand_data_reg <= 16'h00A5; // comment" in new


def test_widens_blocking_assignment():
    code = (
        "reg [7:0] x;\n"
        "always @* x = 4'b1010;\n"
    )
    new, fixed = fix_source(code, [2])
    assert fixed == [2]
    assert "x = 8'b00001010;" in new


def test_does_not_fire_when_target_width_is_unknown():
    code = "always @* unknown_reg <= 8'hA5;"
    new, fixed = fix_source(code, [1])
    assert fixed == []
    assert new == code


def test_does_not_fire_when_rhs_is_not_narrower_literal():
    code = (
        "reg [7:0] x;\n"
        "always @* x <= y + 8'hA5;\n"
    )
    new, fixed = fix_source(code, [2])
    assert fixed == []
    assert new == code


def test_does_not_fire_when_target_width_equals_or_smaller():
    code = (
        "reg [7:0] x;\n"
        "always @* x <= 8'hA5;\n"
    )
    new, fixed = fix_source(code, [2])
    assert fixed == []
    assert new == code


def test_only_flagged_line_is_changed():
    code = (
        "reg [15:0] a, b;\n"
        "always @* begin\n"
        "  a <= 8'hA5;\n"
        "  b <= 8'hA5;\n"
        "end\n"
    )
    new, fixed = fix_source(code, [3])
    assert fixed == [3]
    lines = new.splitlines()
    assert "16'h00A5" in lines[2]
    assert "8'hA5" in lines[3]
