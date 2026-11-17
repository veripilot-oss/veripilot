"""Tests for writing the `lint` section of results.json."""

import json
import sys
from pathlib import Path

import pytest

from lint.linter import build_lint_section, run_all_lint, write_lint_section

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_results_schema import validate  # noqa: E402

EXAMPLES = ROOT / "examples"

LINT_DATA = {
    "verilator_version": "5.034",
    "designs": [
        {
            "name": "fifo",
            "findings": [
                {"rule": "UNUSEDSIGNAL", "file": "buggy/fifo.v", "line": 39, "severity": "warning",
                 "message": "Signal is not driven, nor used: 'lap_counter_reg'", "matched_bug_id": 3},
                {"rule": "LATCH", "file": "buggy/fifo.v", "line": 99, "severity": "warning",
                 "message": "Latch inferred", "matched_bug_id": None},
            ],
        },
        {"name": "spi", "findings": []},
    ],
}


def test_section_follows_schema():
    section = build_lint_section(LINT_DATA, EXAMPLES)
    first = section["warnings"][0]
    assert first == {
        "design": "fifo", "rule": "UNUSEDSIGNAL", "file": "examples/fifo/buggy/fifo.v", "line": 39,
        "severity": "warning", "message": "Signal is not driven, nor used: 'lap_counter_reg'", "matched_bug_id": 3,
    }
    assert section["warnings"][1]["matched_bug_id"] is None
    assert section["generated_at"].endswith("Z")


def test_creates_file_and_validates(tmp_path):
    path = tmp_path / "results" / "results.json"
    doc = write_lint_section(path, LINT_DATA, EXAMPLES)
    assert json.loads(path.read_text(encoding="utf-8")) == doc
    assert doc["schema_version"] == 1
    assert doc["run"]["verilator_version"] == "5.034"
    assert validate(doc) == []


def test_keeps_other_sections_and_replaces_old_lint(tmp_path):
    path = tmp_path / "results.json"
    before = json.loads((ROOT / "examples" / "results.example.json").read_text(encoding="utf-8"))
    path.write_text(json.dumps(before), encoding="utf-8")

    after = write_lint_section(path, LINT_DATA, EXAMPLES)

    for key, value in before.items():
        if key != "lint":
            assert after[key] == value, f"section {key} was changed"
    assert len(after["lint"]["warnings"]) == 2  # replaced, not appended to the example's two
    assert after["lint"]["generated_at"] != before["lint"]["generated_at"]
    assert validate(after) == []


def test_corrupt_file_fails_and_is_left_alone(tmp_path):
    path = tmp_path / "results.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Cannot update corrupt"):
        write_lint_section(path, LINT_DATA, EXAMPLES)
    assert path.read_text(encoding="utf-8") == "{not json"


def test_real_linter_output_is_schema_valid(tmp_path):
    data = run_all_lint(str(EXAMPLES), str(tmp_path / "lint.json"))
    doc = write_lint_section(tmp_path / "results.json", data, EXAMPLES)
    assert validate(doc) == []
    assert len(doc["lint"]["warnings"]) > 0
    assert all(w["file"].startswith("examples/") and "\\" not in w["file"] for w in doc["lint"]["warnings"])
    designs = {w["design"] for w in doc["lint"]["warnings"]}
    assert designs == {"fifo", "spi", "timer"}
