import unittest
from pathlib import Path
import tempfile
from coverage_advisor.advisor import parse_annotated_coverage


class TestCoverageAdvisor(unittest.TestCase):
    def test_parse_annotated_coverage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            rtl_file = Path("fifo.v")
            annotated_file = tmp_path / "fifo.v"

            content = (
                " 000005 module fifo;\n"
                "%000000   reg error_flag;\n"
                " 000010   always @(posedge clk) begin\n"
                "######     state <= NEXT;\n"
                " 000002   end\n"
                "endmodule\n"
            )
            annotated_file.write_text(content, encoding="utf-8")

            pct, uncovered = parse_annotated_coverage(tmp_path, rtl_file)
            self.assertGreater(pct, 0)
            self.assertEqual(len(uncovered), 2)
            self.assertEqual(uncovered[0]["line"], 2)
            self.assertEqual(uncovered[1]["line"], 4)


if __name__ == "__main__":
    unittest.main()
