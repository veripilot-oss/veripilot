"""Tests for `python -m health`."""

import json
import sys
from pathlib import Path

import pytest

from health.__main__ import main, write_health_section

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_results_schema import validate  # noqa: E402

EXAMPLE = ROOT / "examples" / "results.example.json"


def _doc_without_health():
    doc = json.loads(EXAMPLE.read_text(encoding="utf-8"))
    doc.pop("health")
    return doc


def test_writes_health_and_keeps_other_sections(tmp_path):
    path = tmp_path / "results.json"
    before = _doc_without_health()
    path.write_text(json.dumps(before), encoding="utf-8")

    section = write_health_section(path)

    after = json.loads(path.read_text(encoding="utf-8"))
    assert after["health"] == section
    assert section["score"] == 76.6  # same inputs as examples/results.example.json
    for key, value in before.items():
        assert after[key] == value
    assert validate(after) == []


def test_replaces_old_health(tmp_path):
    path = tmp_path / "results.json"
    doc = _doc_without_health()
    doc["health"] = {"generated_at": "2020-01-01T00:00:00Z", "score": 1.0}
    path.write_text(json.dumps(doc), encoding="utf-8")
    write_health_section(path)
    assert json.loads(path.read_text(encoding="utf-8"))["health"]["score"] == 76.6


def test_nothing_measurable_writes_no_section(tmp_path):
    path = tmp_path / "results.json"
    path.write_text(json.dumps({"schema_version": 1, "run": {"id": "x", "started_at": "2026-01-01T00:00:00Z", "verilator_version": "5.034"}}), encoding="utf-8")
    assert write_health_section(path) is None
    assert "health" not in json.loads(path.read_text(encoding="utf-8"))


def test_corrupt_file_fails_clearly(tmp_path, capsys):
    path = tmp_path / "results.json"
    path.write_text("{not json", encoding="utf-8")
    assert main(["--results", str(path)]) == 1
    assert "corrupt" in capsys.readouterr().err
    assert path.read_text(encoding="utf-8") == "{not json"  # file left alone


def test_missing_file_fails_clearly(tmp_path, capsys):
    assert main(["--results", str(tmp_path / "nope.json")]) == 1
    assert "not found" in capsys.readouterr().err
