"""Tests for autofix/pinmissing.py."""

from autofix.pinmissing import fix_source

WAIVED = ("/* verilator lint_off PINCONNECTEMPTY */ .{}() "
          "/* verilator lint_on PINCONNECTEMPTY */")


def test_output_port_multiline_close_on_later_line():
    src = """module sub(input wire [15:0] din, output wire parity_err);
    assign parity_err = ^din;
endmodule

module top;
    wire [15:0] data = 0;
    sub u_parity (
        .din(data)
    );
endmodule"""
    new, fixed = fix_source(src, [7])
    assert fixed == [8]
    assert new.split("\n")[7] == "        .din(data), " + WAIVED.format("parity_err")
    assert new.split("\n")[8] == "    );"
    assert len(new.split("\n")) == len(src.split("\n"))


def test_no_fire_on_missing_scalar_input():
    # a forgotten input (an enable, say) must not be tied off: that would hide the bug
    src = """module child(input wire enable, input wire [7:0] din);
endmodule

module top;
    child u_c (
        .din(8'h55)
    );
endmodule"""
    assert fix_source(src, [5]) == (src, [])


def test_no_fire_on_missing_vector_input():
    src = """module child(input wire [3:0] mask, output wire ready);
endmodule

module top;
    wire r;
    child u_c (
        .ready(r)
    );
endmodule"""
    assert fix_source(src, [6]) == (src, [])


def test_no_fire_when_input_and_output_both_missing():
    # all-or-nothing: the output is not added if an input is missing too
    src = """module child(input wire en, output wire q);
endmodule

module top;
    child u_c (
    );
endmodule"""
    assert fix_source(src, [5]) == (src, [])


def test_output_with_parameterized_module():
    src = """module child #(parameter W = 8) (input wire [W-1:0] d, output wire q);
endmodule

module top;
    wire [3:0] x;
    child #(.W(4)) u_c (
        .d(x)
    );
endmodule"""
    new, fixed = fix_source(src, [6])
    assert fixed == [7]
    assert ".d(x), " + WAIVED.format("q") in new


def test_close_paren_on_same_line_as_last_connection():
    src = """module sub(input wire a, output wire b);
endmodule

module top;
    sub u_sub (
        .a(1'b1));
endmodule"""
    new, fixed = fix_source(src, [5])
    assert fixed == [6]
    assert new.split("\n")[5] == "        .a(1'b1), " + WAIVED.format("b") + ");"


def test_single_line_instance():
    src = """module sub(input wire a, output wire b);
endmodule

module top;
    sub u_sub (.a(1'b1));
endmodule"""
    new, fixed = fix_source(src, [5])
    assert fixed == [5]
    assert "    sub u_sub (.a(1'b1), " + WAIVED.format("b") + ");" in new


def test_trailing_comment_kept():
    src = """module sub(input wire a, output wire b);
endmodule

module top;
    // Important instance
    sub u_sub (
        .a(x) // input data
    );
endmodule"""
    new, fixed = fix_source(src, [6])
    assert fixed == [7]
    assert "// Important instance" in new
    assert new.split("\n")[6] == "        .a(x), " + WAIVED.format("b") + " // input data"


def test_only_flagged_instance_changes():
    src = """module sub(input wire a, output wire b);
endmodule

module top;
    sub u1 (
        .a(1'b1)
    );
    sub u2 (
        .a(1'b0)
    );
endmodule"""
    new, fixed = fix_source(src, [8])
    assert fixed == [9]
    assert new.split("\n")[5] == "        .a(1'b1)"


def test_no_fire_when_all_ports_connected():
    src = """module child(input wire a, output wire b);
endmodule

module top;
    child u_c (
        .a(1'b1),
        .b()
    );
endmodule"""
    assert fix_source(src, [5]) == (src, [])


def test_no_fire_on_inout():
    src = """module bus_slave(inout wire sda, input wire scl);
endmodule

module top;
    bus_slave u_slave (
        .scl(clk)
    );
endmodule"""
    assert fix_source(src, [5]) == (src, [])


def test_no_fire_when_module_not_in_file():
    src = """module top;
    unknown_module u_unk (
        .a(1)
    );
endmodule"""
    assert fix_source(src, [2]) == (src, [])


def test_no_fire_when_module_defined_twice():
    src = """module sub(input wire a, output wire b);
endmodule
module sub(input wire a);
endmodule

module top;
    sub u (
        .a(1'b1)
    );
endmodule"""
    assert fix_source(src, [7]) == (src, [])


def test_no_fire_on_positional_or_wildcard():
    src = """module sub(input wire a, output wire b);
endmodule

module top;
    sub u1 (x);
    sub u2 (.*);
endmodule"""
    assert fix_source(src, [5, 6]) == (src, [])


def test_no_fire_on_non_instance_line():
    src = """module sub(input wire a, output wire b);
endmodule

module top;
    assign y = 1'b0;
endmodule"""
    assert fix_source(src, [5]) == (src, [])
