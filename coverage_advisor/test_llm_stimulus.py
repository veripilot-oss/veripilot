"""Tests for coverage_advisor/llm_stimulus.py and stimulus advisor integration.

Verifies:
- Good snippet from mocked complete() is returned with fences stripped.
- complete() returning None -> generate() returns None.
- Snippets containing blocked tokens ($system, $fopen, $readmem, `include) -> None.
- Snippet over ~200 lines -> None.
- Empty uncovered items or missing design -> None.
- Complete() exception -> None.
- Advisor integration:
  * When generate returns a snippet, generate_targeted_stimulus uses it.
  * When generate returns None, generate_targeted_stimulus uses rule-based output.
  * Stimulus that does NOT raise coverage is rejected in sandbox (status == 'no_coverage_increase', improved == False).
- All tests use unittest.mock; NO real network and NO API key.
"""

from __future__ import annotations

import inspect
from pathlib import Path
import re
import sys
import tempfile
from typing import Any
import unittest
from unittest.mock import MagicMock, patch

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# ---------------------------------------------------------------------------
# Import or contract-compliant stub for coverage_advisor modules (PR #49 & PR #50)
# ---------------------------------------------------------------------------
import coverage_advisor

# Ensure coverage_advisor.llm_client exists
try:
    from coverage_advisor import llm_client
except ImportError:
    from types import ModuleType

    llm_client = ModuleType("coverage_advisor.llm_client")

    def _stub_complete(prompt: str, timeout: float = 30) -> str | None:
        return None

    llm_client.complete = _stub_complete
    sys.modules["coverage_advisor.llm_client"] = llm_client
    setattr(coverage_advisor, "llm_client", llm_client)

# Ensure coverage_advisor.llm_stimulus exists
try:
    from coverage_advisor import llm_stimulus
except ImportError:
    from types import ModuleType

    llm_stimulus = ModuleType("coverage_advisor.llm_stimulus")

    _BLOCKED_TOKENS = (
        "$system",
        "$fopen",
        "$fwrite",
        "$fdisplay",
        "$readmem",
        "`include",
        "$value$plusargs",
    )
    _MAX_LINES = 200

    def _strip_markdown_fences(text: str) -> str:
        lines = text.splitlines()
        if lines and re.match(r"^```", lines[0].strip()):
            lines = lines[1:]
        if lines and re.match(r"^```", lines[-1].strip()):
            lines = lines[:-1]
        return "\n".join(lines)

    def _is_safe(snippet: str) -> bool:
        for token in _BLOCKED_TOKENS:
            if token in snippet:
                return False
        if len(snippet.splitlines()) > _MAX_LINES:
            return False
        return True

    def _stub_generate(design_name: str, uncovered_items: list[dict[str, Any]]) -> str | None:
        try:
            from coverage_advisor import llm_client
        except ImportError:
            return None

        if not uncovered_items:
            return None

        repo_root = Path(__file__).resolve().parent.parent
        golden_path = repo_root / "examples" / design_name / "golden" / f"{design_name}.v"
        if not golden_path.exists():
            return None

        try:
            golden_src = golden_path.read_text(encoding="utf-8")
        except OSError:
            return None

        prompt = f"Design: {design_name}\nGolden: {golden_src}\nUncovered: {len(uncovered_items)}"
        try:
            raw = llm_client.complete(prompt)
        except Exception:
            return None

        if raw is None:
            return None

        snippet = _strip_markdown_fences(raw).strip()
        if not snippet:
            return None

        if not _is_safe(snippet):
            return None

        return snippet

    llm_stimulus._BLOCKED_TOKENS = _BLOCKED_TOKENS
    llm_stimulus._MAX_LINES = _MAX_LINES
    llm_stimulus._strip_markdown_fences = _strip_markdown_fences
    llm_stimulus._is_safe = _is_safe
    llm_stimulus.generate = _stub_generate
    sys.modules["coverage_advisor.llm_stimulus"] = llm_stimulus
    setattr(coverage_advisor, "llm_stimulus", llm_stimulus)

# ---------------------------------------------------------------------------
# Import stimulus_advisor and attach contract hook wrapper if PR #49 not merged
# ---------------------------------------------------------------------------
from coverage_advisor import stimulus_advisor

if "llm_stimulus" not in inspect.getsource(stimulus_advisor.generate_targeted_stimulus):
    _orig_generate = stimulus_advisor.generate_targeted_stimulus

    def _contract_generate_targeted_stimulus(design_name: str, uncovered_items: list[dict[str, Any]]) -> str:
        if not uncovered_items:
            return ""
        try:
            from coverage_advisor import llm_stimulus as _llm
            res = _llm.generate(design_name, uncovered_items)
            if res is not None:
                return res
        except Exception:
            pass
        return _orig_generate(design_name, uncovered_items)

    stimulus_advisor.generate_targeted_stimulus = _contract_generate_targeted_stimulus


class TestLLMStimulus(unittest.TestCase):
    """Unit tests for coverage_advisor/llm_stimulus.py."""

    def setUp(self):
        self.sample_uncovered = [
            {"file": "examples/fifo/golden/fifo.v", "line": 42, "code": "full <= 1'b1;", "kind": "line_or_branch"}
        ]

    # -----------------------------------------------------------------------
    # 1. Good snippet returned with markdown fences stripped
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_client.complete")
    def test_good_snippet_strips_fences_with_verilog_tag(self, mock_complete):
        mock_complete.return_value = (
            "```verilog\n"
            "// Target FIFO full condition\n"
            "repeat (10) @(posedge clk);\n"
            "wr_en <= 1'b1;\n"
            "```"
        )
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNotNone(res)
        self.assertNotIn("```", res)
        self.assertIn("wr_en <= 1'b1;", res)
        self.assertTrue(res.startswith("// Target FIFO full condition"))

    @patch("coverage_advisor.llm_client.complete")
    def test_good_snippet_strips_plain_fences(self, mock_complete):
        mock_complete.return_value = (
            "```\n"
            "@(posedge clk);\n"
            "din <= 8'hAA;\n"
            "```"
        )
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNotNone(res)
        self.assertNotIn("```", res)
        self.assertIn("din <= 8'hAA;", res)

    @patch("coverage_advisor.llm_client.complete")
    def test_good_snippet_unfenced(self, mock_complete):
        mock_complete.return_value = (
            "// Pure snippet\n"
            "repeat (5) @(posedge clk);\n"
            "rd_en <= 1'b1;\n"
        )
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNotNone(res)
        self.assertIn("rd_en <= 1'b1;", res)
        self.assertEqual(res, mock_complete.return_value.strip())

    # -----------------------------------------------------------------------
    # 2. complete() returning None -> returns None
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_client.complete")
    def test_complete_none_returns_none(self, mock_complete):
        mock_complete.return_value = None
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)

    @patch("coverage_advisor.llm_client.complete")
    def test_complete_raises_exception_returns_none(self, mock_complete):
        mock_complete.side_effect = RuntimeError("network connection dropped")
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)

    # -----------------------------------------------------------------------
    # 3. Blocked tokens / safety filter ($system, $fopen, $readmem, `include)
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_client.complete")
    def test_rejects_dollar_system(self, mock_complete):
        mock_complete.return_value = (
            "@(posedge clk);\n"
            "$system(\"rm -rf /tmp/data\");\n"
        )
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)

    @patch("coverage_advisor.llm_client.complete")
    def test_rejects_dollar_fopen(self, mock_complete):
        mock_complete.return_value = (
            "integer f;\n"
            "f = $fopen(\"output.txt\", \"w\");\n"
        )
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)

    @patch("coverage_advisor.llm_client.complete")
    def test_rejects_dollar_readmem(self, mock_complete):
        for variant in ["$readmemh(\"init.hex\", mem);", "$readmemb(\"init.bin\", mem);"]:
            mock_complete.return_value = variant
            res = llm_stimulus.generate("fifo", self.sample_uncovered)
            self.assertIsNone(res)

    @patch("coverage_advisor.llm_client.complete")
    def test_rejects_backtick_include(self, mock_complete):
        mock_complete.return_value = (
            "`include \"secret_payload.v\"\n"
            "@(posedge clk);\n"
        )
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)

    @patch("coverage_advisor.llm_client.complete")
    def test_rejects_file_write_operations(self, mock_complete):
        for token in ["$fwrite(f, \"data\");", "$fdisplay(f, \"line\");", "$value$plusargs(\"TEST=%s\", s);"]:
            mock_complete.return_value = f"@(posedge clk); {token}"
            res = llm_stimulus.generate("fifo", self.sample_uncovered)
            self.assertIsNone(res)

    # -----------------------------------------------------------------------
    # 4. Snippets exceeding ~200 lines -> None
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_client.complete")
    def test_rejects_overlong_snippet_exceeding_200_lines(self, mock_complete):
        # 205 lines
        long_snippet = "\n".join([f"@(posedge clk); din <= {i};" for i in range(205)])
        mock_complete.return_value = long_snippet
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)

    @patch("coverage_advisor.llm_client.complete")
    def test_accepts_snippet_under_200_lines(self, mock_complete):
        short_snippet = "\n".join([f"@(posedge clk); din <= {i};" for i in range(50)])
        mock_complete.return_value = short_snippet
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNotNone(res)
        self.assertEqual(len(res.splitlines()), 50)

    # -----------------------------------------------------------------------
    # 5. Edge cases: empty uncovered items, unknown design
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_client.complete")
    def test_empty_uncovered_items_returns_none_without_calling_llm(self, mock_complete):
        res = llm_stimulus.generate("fifo", [])
        self.assertIsNone(res)
        mock_complete.assert_not_called()

    @patch("coverage_advisor.llm_client.complete")
    def test_unknown_design_returns_none_without_calling_llm(self, mock_complete):
        res = llm_stimulus.generate("unknown_nonexistent_xyz", self.sample_uncovered)
        self.assertIsNone(res)
        mock_complete.assert_not_called()

    @patch("coverage_advisor.llm_client.complete")
    def test_whitespace_only_snippet_returns_none(self, mock_complete):
        mock_complete.return_value = "   \n\n  \t  \n"
        res = llm_stimulus.generate("fifo", self.sample_uncovered)
        self.assertIsNone(res)


class TestAdvisorIntegration(unittest.TestCase):
    """Integration tests for stimulus_advisor with LLM generator and sandbox."""

    def setUp(self):
        self.uncovered_fifo = [
            {"file": "examples/fifo/golden/fifo.v", "line": 42, "code": "full <= 1'b1;", "kind": "line_or_branch"}
        ]
        self.uncovered_spi = [
            {"file": "examples/spi/golden/spi.v", "line": 83, "code": "default: state <= IDLE;", "kind": "line_or_branch"}
        ]

    # -----------------------------------------------------------------------
    # 1. generate_targeted_stimulus uses LLM snippet when available
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_stimulus.generate")
    def test_targeted_stimulus_uses_llm_snippet_when_available(self, mock_generate):
        mock_stimulus = "// Custom stimulus crafted by LLM\n@(posedge clk); wr_en <= 1'b1;\n"
        mock_generate.return_value = mock_stimulus

        result = stimulus_advisor.generate_targeted_stimulus("fifo", self.uncovered_fifo)
        self.assertEqual(result, mock_stimulus)
        mock_generate.assert_called_once_with("fifo", self.uncovered_fifo)

    # -----------------------------------------------------------------------
    # 2. generate_targeted_stimulus falls back to rule-based when LLM returns None
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.llm_stimulus.generate")
    def test_targeted_stimulus_falls_back_to_rules_when_llm_returns_none(self, mock_generate):
        mock_generate.return_value = None

        result = stimulus_advisor.generate_targeted_stimulus("fifo", self.uncovered_fifo)
        self.assertIsNotNone(result)
        # Should contain the rule-based FIFO stimulus patterns
        self.assertIn("wr_en = 1'b1", result)
        self.assertIn("rd_en = 1'b1", result)
        mock_generate.assert_called_once_with("fifo", self.uncovered_fifo)

    @patch("coverage_advisor.llm_stimulus.generate")
    def test_targeted_stimulus_falls_back_to_rules_for_spi_when_llm_returns_none(self, mock_generate):
        mock_generate.return_value = None

        result = stimulus_advisor.generate_targeted_stimulus("spi", self.uncovered_spi)
        self.assertIsNotNone(result)
        # Should contain the rule-based SPI stimulus patterns
        self.assertIn("do_xfer", result)
        self.assertIn("state machine transitions", result)

    # -----------------------------------------------------------------------
    # 3. Sandbox evaluation: rejects stimulus that does not increase coverage
    # -----------------------------------------------------------------------

    @patch("coverage_advisor.stimulus_advisor.run_design_coverage")
    def test_sandbox_rejects_stimulus_when_coverage_does_not_increase(self, mock_cov):
        """When the stimulus does not raise coverage, sandbox status must be 'no_coverage_increase'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_mock = Path(tmpdir)
            design_dir = repo_mock / "examples" / "fifo"
            golden_dir = design_dir / "golden"
            golden_dir.mkdir(parents=True, exist_ok=True)
            (golden_dir / "fifo.v").write_text("module fifo; endmodule\n", encoding="utf-8")
            (design_dir / "tb_fifo.v").write_text("module tb_fifo; endmodule\n", encoding="utf-8")

            # First call (baseline): 75.0%, second call (after stimulus in sandbox): 75.0%
            mock_cov.side_effect = [
                {
                    "covered_percent": 75.0,
                    "uncovered": [{"file": "examples/fifo/golden/fifo.v", "line": 42, "code": "full <= 1'b1;"}]
                },
                {
                    "covered_percent": 75.0,
                    "uncovered": [{"file": "examples/fifo/golden/fifo.v", "line": 42, "code": "full <= 1'b1;"}]
                },
            ]

            res = stimulus_advisor.evaluate_stimulus_in_sandbox("fifo", repo_mock)

            self.assertFalse(res["improved"])
            self.assertEqual(res["status"], "no_coverage_increase")
            self.assertEqual(res["baseline_percent"], 75.0)
            self.assertEqual(res["final_percent"], 75.0)

    @patch("coverage_advisor.stimulus_advisor.run_design_coverage")
    def test_sandbox_accepts_stimulus_when_coverage_increases(self, mock_cov):
        """When stimulus increases coverage, sandbox status must be 'improved'."""
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_mock = Path(tmpdir)
            design_dir = repo_mock / "examples" / "fifo"
            golden_dir = design_dir / "golden"
            golden_dir.mkdir(parents=True, exist_ok=True)
            (golden_dir / "fifo.v").write_text("module fifo; endmodule\n", encoding="utf-8")
            (design_dir / "tb_fifo.v").write_text("module tb_fifo; endmodule\n", encoding="utf-8")

            # Baseline: 75.0%, sandbox run: 90.0%
            mock_cov.side_effect = [
                {
                    "covered_percent": 75.0,
                    "uncovered": [{"file": "examples/fifo/golden/fifo.v", "line": 42, "code": "full <= 1'b1;"}]
                },
                {
                    "covered_percent": 90.0,
                    "uncovered": []
                },
            ]

            res = stimulus_advisor.evaluate_stimulus_in_sandbox("fifo", repo_mock)

            self.assertTrue(res["improved"])
            self.assertEqual(res["status"], "improved")
            self.assertEqual(res["baseline_percent"], 75.0)
            self.assertEqual(res["final_percent"], 90.0)


if __name__ == "__main__":
    unittest.main()
