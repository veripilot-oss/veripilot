import unittest
from pathlib import Path
import tempfile
from coverage_advisor.advisor import parse_annotated_coverage, is_declaration_line


class TestCoverageAdvisor(unittest.TestCase):
    def test_is_declaration_line(self):
        self.assertTrue(is_declaration_line("input wire reset,"))
        self.assertTrue(is_declaration_line("output wire [7:0] data_out,"))
        self.assertTrue(is_declaration_line("wire clk;"))
        self.assertTrue(is_declaration_line("reg [15:0] counter;"))
        self.assertTrue(is_declaration_line("localparam IDLE=2'b00;"))
        self.assertTrue(is_declaration_line("module fifo;"))
        self.assertTrue(is_declaration_line("endmodule"))
        self.assertTrue(is_declaration_line("// comments"))
        self.assertFalse(is_declaration_line("state <= IDLE;"))
        self.assertFalse(is_declaration_line("if (start) begin"))
        self.assertFalse(is_declaration_line("assign done = (state == DONE);"))

    def test_parse_annotated_coverage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repo_root = tmp_path
            examples_dir = repo_root / "examples" / "fifo" / "golden"
            examples_dir.mkdir(parents=True, exist_ok=True)
            rtl_file = examples_dir / "fifo.v"
            annotated_dir = repo_root / "annotated"
            annotated_dir.mkdir(parents=True, exist_ok=True)
            annotated_file = annotated_dir / "fifo.v"

            content = (
                " 000005 module fifo;\n"
                "%000000   input wire reset,\n"  # should be filtered as declaration
                "%000000   reg error_flag;\n"   # should be filtered as declaration
                " 000010   always @(posedge clk) begin\n"
                "######     state <= NEXT;\n"     # uncovered statement/branch
                " 000002   end\n"
                "endmodule\n"
            )
            annotated_file.write_text(content, encoding="utf-8")

            pct, uncovered = parse_annotated_coverage(annotated_dir, rtl_file, repo_root=repo_root)
            self.assertGreater(pct, 0)
            self.assertEqual(len(uncovered), 1)
            self.assertEqual(uncovered[0]["line"], 5)
            self.assertEqual(uncovered[0]["file"], "examples/fifo/golden/fifo.v")
            self.assertIn("state <= NEXT;", uncovered[0]["code"])


if __name__ == "__main__":
    unittest.main()
