"""Test suite for the VeriPilot lint tool."""

from pathlib import Path
from lint.linter import lint_design, run_all_lint


def test_lint_fifo_counts(tmp_path):
    repo_root = Path(__file__).parent.parent
    examples_dir = repo_root / "examples"
    
    fifo_buggy = examples_dir / "fifo" / "buggy" / "fifo.v"
    target_examples = examples_dir
    if not fifo_buggy.exists():
        target_examples = Path("/tmp/test_examples")

    res = lint_design("fifo", target_examples)
    assert res["name"] == "fifo"
    assert res["planted"] == 14
    assert res["detected"] >= 12
    assert len(res["findings"]) > 0

    out_file = tmp_path / "results" / "lint.json"
    data = run_all_lint(target_examples, out_file)
    assert data["schema_version"] == 1
    assert data["verilator_version"] == "5.034"
    assert "designs" in data
    assert "totals" in data
    assert data["totals"]["planted"] >= 14
    assert data["totals"]["detected"] >= 12
    assert out_file.exists()
