import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coverage_advisor.stimulus_advisor import (
    extract_uncovered_context,
    generate_targeted_stimulus,
    patch_testbench_content,
    evaluate_stimulus_in_sandbox,
    update_results_json,
)


class TestStimulusAdvisor(unittest.TestCase):
    def test_extract_uncovered_context(self):
        uncovered = [
            {"file": "examples/spi/golden/spi.v", "line": 83, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]
        ctx = extract_uncovered_context(uncovered)
        self.assertIn("Line 83: default: state <= IDLE;", ctx)

    def test_extract_uncovered_context_empty(self):
        ctx = extract_uncovered_context([])
        self.assertEqual(ctx, "No uncovered lines.")

    def test_generate_targeted_stimulus_spi(self):
        # Dynamically matches context (default/state keywords) regardless of line number
        uncovered = [
            {"file": "examples/spi/golden/spi.v", "line": 120, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]
        stim = generate_targeted_stimulus("spi", uncovered)
        self.assertIn("do_xfer", stim)
        self.assertIn("state machine transitions", stim)

    def test_generate_targeted_stimulus_timer(self):
        # Dynamically matches context (counter/timer/default) regardless of line number
        uncovered = [
            {"file": "examples/timer/golden/timer.v", "line": 99, "code": "default: next_state = IDLE;", "kind": "line_or_branch"}
        ]
        stim = generate_targeted_stimulus("timer", uncovered)
        self.assertIn("drive", stim)
        self.assertIn("zero-count", stim)

    def test_generate_targeted_stimulus_fifo(self):
        # Dynamically matches FIFO boundary context
        uncovered = [
            {"file": "examples/fifo/golden/fifo.v", "line": 42, "code": "full <= 1'b1;", "kind": "line_or_branch"}
        ]
        stim = generate_targeted_stimulus("fifo", uncovered)
        self.assertIn("wr_en = 1'b1", stim)
        self.assertIn("rd_en = 1'b1", stim)

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

    @patch("coverage_advisor.stimulus_advisor.run_design_coverage")
    def test_evaluate_stimulus_already_clean(self, mock_cov):
        mock_cov.return_value = {"covered_percent": 100.0, "uncovered": []}
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_mock = Path(tmpdir)
            design_dir = repo_mock / "examples" / "fifo"
            golden_dir = design_dir / "golden"
            golden_dir.mkdir(parents=True, exist_ok=True)
            (golden_dir / "fifo.v").write_text("module fifo; endmodule\n", encoding="utf-8")
            (design_dir / "tb_fifo.v").write_text("module tb_fifo; endmodule\n", encoding="utf-8")

            res = evaluate_stimulus_in_sandbox("fifo", repo_mock)
            self.assertEqual(res["status"], "already_clean")
            self.assertFalse(res["improved"])
            self.assertEqual(res["baseline_percent"], 100.0)

    @patch("coverage_advisor.stimulus_advisor.run_design_coverage")
    def test_evaluate_stimulus_preserves_examples_directory(self, mock_cov):
        """Verify evaluate_stimulus_in_sandbox leaves examples/ untouched while reporting results."""
        # Baseline returns 80%, sandbox run returns 90% (improved)
        mock_cov.side_effect = [
            {
                "covered_percent": 80.0,
                "uncovered": [{"file": "examples/spi/golden/spi.v", "line": 83, "code": "default: state <= IDLE;"}]
            },
            {
                "covered_percent": 90.0,
                "uncovered": []
            }
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            repo_mock = Path(tmpdir)
            design_dir = repo_mock / "examples" / "spi"
            golden_dir = design_dir / "golden"
            golden_dir.mkdir(parents=True, exist_ok=True)

            rtl_file = golden_dir / "spi.v"
            initial_rtl_content = "module spi(input clk); endmodule\n"
            rtl_file.write_text(initial_rtl_content, encoding="utf-8")

            tb_file = design_dir / "tb_spi.v"
            initial_tb_content = "module tb_spi; initial begin if (error == 0) $display(\"PASS\"); end endmodule\n"
            tb_file.write_text(initial_tb_content, encoding="utf-8")

            res = evaluate_stimulus_in_sandbox("spi", repo_mock)

            # Strict assertions on return value
            self.assertTrue(res["improved"])
            self.assertEqual(res["status"], "improved")
            self.assertEqual(res["baseline_percent"], 80.0)
            self.assertEqual(res["final_percent"], 90.0)

            # Assert original files in examples/ are strictly unmodified
            self.assertEqual(tb_file.read_text(encoding="utf-8"), initial_tb_content)
            self.assertEqual(rtl_file.read_text(encoding="utf-8"), initial_rtl_content)

    def test_update_results_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = Path(tmpdir) / "results.json"
            summary = {
                "designs": [
                    {
                        "design": "spi",
                        "baseline_percent": 83.33,
                        "final_percent": 83.33,
                        "status": "no_coverage_increase",
                        "improved": False
                    }
                ]
            }
            update_results_json(summary, results_path)
            self.assertTrue(results_path.exists())

            with open(results_path, "r", encoding="utf-8") as f:
                doc = json.load(f)

            self.assertEqual(doc["schema_version"], 1)
            self.assertIn("stimulus", doc)
            self.assertEqual(doc["stimulus"]["designs"][0]["design"], "spi")

    def test_update_results_json_corrupt_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results_path = Path(tmpdir) / "results.json"
            results_path.write_text("corrupted non json {", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                update_results_json({"designs": []}, results_path)


if __name__ == "__main__":
    unittest.main()
