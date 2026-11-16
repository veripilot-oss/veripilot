"""Test suite for the VeriPilot lint tool."""

import os
from pathlib import Path
from lint.linter import lint_design, run_all_lint


def test_lint_fifo_counts(tmp_path):
    repo_root = Path(__file__).resolve().parent.parent
    examples_dir = repo_root / "examples"

    fifo_buggy = examples_dir / "fifo" / "buggy" / "fifo.v"
    target_examples = examples_dir
    if not fifo_buggy.exists():
        # Fall back to environment variable or local test cache if not in repo
        env_examples = os.environ.get("VERIPILOT_EXAMPLES_DIR")
        if env_examples and Path(env_examples).exists():
            target_examples = Path(env_examples)
        else:
            target_examples = Path("/tmp/test_examples")

    # Pass resolved absolute path to verify path regex handles absolute paths
    res = lint_design("fifo", target_examples.resolve())
    assert res["name"] == "fifo"
    assert res["planted"] == 14
    assert res["detected"] >= 12
    assert len(res["findings"]) > 0

    out_file = tmp_path / "results" / "lint.json"
    data = run_all_lint(str(target_examples.resolve()), str(out_file.resolve()))
    assert data["schema_version"] == 1
    assert data["verilator_version"] == "5.034"
    assert "designs" in data
    assert "totals" in data
    assert data["totals"]["planted"] >= 14
    assert data["totals"]["detected"] >= 12
    assert out_file.exists()
