"""Tests for the regression runner."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from regress import runner

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from test_results_schema import validate  # noqa: E402


def test_classify():
    assert runner.classify(0, "PASS\n") == "pass"
    assert runner.classify(0, "") == "fail"                       # no PASS line
    assert runner.classify(1, "PASS\n") == "fail"                 # bad exit
    assert runner.classify(0, "FAIL: x\nPASS\n") == "fail"        # FAIL seen


def test_write_section_keeps_other_sections(tmp_path):
    out = tmp_path / "results.json"
    out.write_text(json.dumps({
        "schema_version": 1,
        "run": {"id": "r", "started_at": "2026-01-01T00:00:00Z", "verilator_version": "5.034"},
        "coverage": {"generated_at": "2026-01-01T00:00:00Z", "designs": []},
    }))
    tests = [{"design": "fifo", "test": "tb_fifo", "status": "pass", "seed": 1, "duration_s": 0.1}]
    doc = runner.write_section(out, tests, "5.034")
    assert doc["coverage"]["designs"] == []
    assert doc["run"]["id"] == "r"
    assert json.loads(out.read_text())["regression"]["tests"] == tests
    assert validate(doc) == []


def test_write_section_creates_valid_file(tmp_path):
    out = tmp_path / "sub" / "results.json"
    runner.write_section(out, [], "5.034")
    assert validate(json.loads(out.read_text())) == []


def _verilator_ok():
    if not shutil.which("verilator"):
        return False
    return runner.verilator_version() == runner.REQUIRED_VERILATOR


@pytest.mark.skipif(not _verilator_ok(), reason="Verilator 5.034 not available")
def test_fifo_end_to_end(tmp_path):
    out = tmp_path / "results.json"
    tests = runner.run("fifo", [1, 2], out)
    assert [t["seed"] for t in tests] == [1, 2]
    assert all(t["status"] == "pass" for t in tests)
    doc = json.loads(out.read_text())
    assert validate(doc) == []
    assert doc["run"]["verilator_version"] == "5.034"
