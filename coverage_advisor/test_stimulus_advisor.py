import unittest
from pathlib import Path
import tempfile
from coverage_advisor.stimulus_advisor import (
    extract_uncovered_context,
    generate_targeted_stimulus,
    patch_testbench_with_stimulus,
)


class TestStimulusAdvisor(unittest.TestCase):
    def test_extract_uncovered_context(self):
        uncovered = [
            {"file": "examples/spi/golden/spi.v", "line": 88, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]
        ctx = extract_uncovered_context("spi", Path("."), uncovered)
        self.assertIn("Line 88: default: state <= IDLE;", ctx)

    def test_generate_targeted_stimulus(self):
        uncovered = [
            {"file": "examples/spi/golden/spi.v", "line": 88, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]
        stim = generate_targeted_stimulus("spi", uncovered)
        self.assertIn("do_xfer", stim)

    def test_patch_testbench_with_stimulus(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tb_file = Path(tmpdir) / "tb_dummy.v"
            tb_file.write_text(
                "module tb;\ninitial begin\n  #10;\n  if (error == 0) $display(\"PASS\");\n  $finish;\nend\nendmodule\n",
                encoding="utf-8"
            )
            stimulus = "  // Extra stimulus\n  #5 clk = 1;\n"
            patched = patch_testbench_with_stimulus(tb_file, stimulus)
            self.assertIn("// Extra stimulus", patched)
            self.assertIn("if (error == 0) $display(\"PASS\");", patched)


if __name__ == "__main__":
    unittest.main()
