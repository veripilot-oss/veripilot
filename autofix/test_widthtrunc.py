"""Tests for autofix/widthtrunc.py."""

from autofix.widthtrunc import fix_source


def test_slices_plain_identifier():
    code = (
        "module m;\n"
        "  reg [3:0] trunc_ptr_reg;\n"
        "  always @(posedge clk) begin\n"
        "    trunc_ptr_reg <= write;\n"
        "  end\n"
        "endmodule"
    )
    new, fixed = fix_source(code, [4])
    assert fixed == [4]
    assert "trunc_ptr_reg <= write[3:0];" in new


def test_slices_with_parameter_expression():
    code = (
        "module m #(\n"
        "  parameter ADDR_WIDTH = 4\n"
        ") ();\n"
        "  reg [ADDR_WIDTH - 1:0] trunc_ptr_reg;\n"
        "  always @(posedge clk) begin\n"
        "    trunc_ptr_reg <= write; // keep comment\n"
        "  end\n"
        "endmodule"
    )
    new, fixed = fix_source(code, [6])
    assert fixed == [6]
    assert "trunc_ptr_reg <= write[3:0]; // keep comment" in new


def test_does_not_fire_when_target_width_is_unknown():
    code = "always @* unknown_reg <= write;"
    new, fixed = fix_source(code, [1])
    assert fixed == []
    assert new == code


def test_does_not_fire_when_rhs_is_complex_expression():
    code = (
        "reg [3:0] r;\n"
        "always @* r <= a + b;\n"
    )
    new, fixed = fix_source(code, [2])
    assert fixed == []
    assert new == code


def test_does_not_fire_when_rhs_already_sliced():
    code = (
        "reg [3:0] r;\n"
        "always @* r <= write[3:0];\n"
    )
    new, fixed = fix_source(code, [2])
    assert fixed == []
    assert new == code


def test_only_flagged_line_is_changed():
    code = (
        "reg [3:0] a, b;\n"
        "always @* begin\n"
        "  a <= write;\n"
        "  b <= write;\n"
        "end\n"
    )
    new, fixed = fix_source(code, [3])
    assert fixed == [3]
    lines = new.splitlines()
    assert "write[3:0]" in lines[2]
    assert "write;" in lines[3]
