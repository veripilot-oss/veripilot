import tempfile
import unittest
from pathlib import Path
from coverage_advisor.stimulus_advisor import (
    extract_uncovered_context,
    generate_targeted_stimulus,
    patch_testbench_content,
    evaluate_stimulus_in_sandbox,
)


class TestStimulusAdvisor(unittest.TestCase):
    def test_extract_uncovered_context(self):
        uncovered = [
            {"file": "examples/spi/golden/spi.v", "line": 88, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]
        ctx = extract_uncovered_context(uncovered)
        self.assertIn("Line 88: default: state <= IDLE;", ctx)

    def test_extract_uncovered_context_empty(self):
        ctx = extract_uncovered_context([])
        self.assertEqual(ctx, "No uncovered lines.")

    def test_generate_targeted_stimulus_spi(self):
        uncovered = [
            {"file": "examples/spi/golden/spi.v", "line": 88, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]
        stim = generate_targeted_stimulus("spi", uncovered)
        self.assertIn("do_xfer", stim)

    def test_generate_targeted_stimulus_timer(self):
        uncovered = [
            {"file": "examples/timer/golden/timer.v", "line": 51, "code": "default: next_state = IDLE;", "kind": "line_or_branch"}
        ]
        stim = generate_targeted_stimulus("timer", uncovered)
        self.assertIn("drive", stim)

    def test_patch_testbench_content(self):
        original = (
            "module tb;\n"
            "initial begin\n"
            "  #10;\n"
            "  if (error == 0) $display(\"PASS\");\n"
            "  $finish;\n"
            "end\n"
            "endmodule\n"
        )
        stimulus = "  // Extra stimulus\n  #5 clk = 1;\n"
        patched = patch_testbench_content(original, stimulus)
        self.assertIn("// Extra stimulus", patched)
        self.assertIn("if (error == 0) $display(\"PASS\");", patched)

    def test_evaluate_stimulus_preserves_examples_directory(self):
        """Verify that evaluate_stimulus_in_sandbox does not modify any files in examples/."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_mock = Path(tmpdir)
            design_dir = repo_mock / "examples" / "dummy"
            golden_dir = design_dir / "golden"
            golden_dir.mkdir(parents=True, exist_ok=True)

            rtl_file = golden_dir / "dummy.v"
            rtl_file.write_text("module dummy(input clk); endmodule\n", encoding="utf-8")

            tb_file = design_dir / "tb_dummy.v"
            initial_tb_content = "module tb_dummy; initial $finish; endmodule\n"
            tb_file.write_text(initial_tb_content, encoding="utf-8")

            # Run mock sandbox evaluation - should not touch original tb_file
            try:
                evaluate_stimulus_in_sandbox("dummy", repo_mock)
            except Exception:
                pass

            # Assert original file was completely untouched
            self.assertEqual(tb_file.read_text(encoding="utf-8"), initial_tb_content)


if __name__ == "__main__":
    unittest.main()
