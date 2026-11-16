"""Tests for autofix/caseincomplete.py."""

from autofix.caseincomplete import fix_source

CASE = (
    "always @(*) begin\n"
    "    case (s)\n"
    "        2'b00: n = 2'b01;\n"
    "        2'b01: n = 2'b10;\n"
    "    endcase\n"
    "end"
)


def test_adds_default_before_endcase():
    new, fixed = fix_source(CASE, [2])
    assert fixed == [2]
    lines = new.split("\n")
    assert lines[4] == "        default: n = '0;"
    assert lines[5] == "    endcase"


def test_existing_default_is_left_alone():
    text = CASE.replace("    endcase", "        default: n = 2'b00;\n    endcase")
    new, fixed = fix_source(text, [2])
    assert new == text
    assert fixed == []


def test_several_targets_get_a_begin_end_block():
    text = (
        "always @(*) begin\n"
        "    case (s)\n"
        "        1'b0: begin a = 1; b = 0; end\n"
        "    endcase\n"
        "end"
    )
    new, _ = fix_source(text, [2])
    assert "default: begin" in new
    assert "a = '0;" in new and "b = '0;" in new


def test_clocked_block_gets_an_empty_default_not_zeroing():
    text = "always @(posedge c) begin\n  case (s)\n    1'b0: q <= d;\n  endcase\nend"
    new, fixed = fix_source(text, [2])
    assert fixed == [2]
    lines = new.split("\n")
    assert lines[3] == "    default: ;"
    assert lines[4] == "  endcase"
    assert "'0" not in new


def test_clocked_block_with_several_targets_still_gets_one_empty_default():
    text = (
        "always @(posedge c) begin\n"
        "  case (s)\n"
        "    1'b0: begin a <= 1; b <= 0; end\n"
        "  endcase\n"
        "end"
    )
    new, _ = fix_source(text, [2])
    assert new.count("default: ;") == 1
    assert "'0" not in new and "begin\n" not in new.split("default")[1]


def test_combinational_block_still_zeroes_the_targets():
    new, _ = fix_source(CASE, [2])
    assert "default: n = '0;" in new


def test_nested_case_uses_the_matching_endcase():
    text = (
        "always @(*) begin\n"
        "  case (s)\n"
        "    0: case (t)\n"
        "         0: n = 1;\n"
        "         default: n = 2;\n"
        "       endcase\n"
        "  endcase\n"
        "end"
    )
    new, fixed = fix_source(text, [2])
    assert fixed == [2]
    lines = new.split("\n")
    assert lines[6].strip() == "default: n = '0;"
    assert lines[7].strip() == "endcase"


def test_line_without_case_is_ignored():
    new, fixed = fix_source("assign y = a;", [1])
    assert new == "assign y = a;"
    assert fixed == []


def test_two_cases_fixed_bottom_up_keep_line_numbers_valid():
    one = "  case (s)\n    0: n = 1;\n  endcase"
    new, fixed = fix_source(one + "\n" + one, [1, 4])
    assert fixed == [1, 4]
    assert new.count("default:") == 2
