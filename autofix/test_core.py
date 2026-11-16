"""Tests for autofix/core.py (engine, results writer, and a run over the real examples)."""

import json
from pathlib import Path

import pytest

from autofix import blkseq, caseincomplete, combdly, core

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
needs_verilator = pytest.mark.skipif(
    not core.have_verilator() or not (EXAMPLES / "fifo" / "buggy" / "fifo.v").exists(),
    reason="needs verilator and the fifo example",
)
ROW_KEYS = {"design", "rule", "file", "line", "before", "after", "verified"}


def test_hunks_map_to_the_warning_line():
    old = "a\ncase\n x\nendcase\nz"
    new = "a\ncase\n x\n default\nendcase\nz"
    assert list(core._hunks(old, new, [2])) == [(2, "", "default")]


def test_hunks_for_in_place_edit():
    assert list(core._hunks("a\nb <= 1;\nc", "a\nb = 1;\nc", [2])) == [(2, "b <= 1;", "b = 1;")]


def test_write_section_replaces_only_autofix(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "_verilator_version", lambda: "5.034")
    out = tmp_path / "r" / "results.json"
    out.parent.mkdir()
    out.write_text(json.dumps({
        "schema_version": 1,
        "run": {"id": "r", "started_at": "2026-01-01T00:00:00Z", "verilator_version": "5.034"},
        "coverage": {"generated_at": "2026-01-01T00:00:00Z", "designs": []},
    }))
    rows = [{"design": "fifo", "rule": "COMBDLY", "file": "x.v", "line": 1,
             "before": "a", "after": "b", "verified": False}]
    doc = core.write_section(out, rows)
    assert doc["coverage"]["designs"] == []
    assert doc["run"]["id"] == "r"
    assert json.loads(out.read_text())["autofix"]["attempts"] == rows


def test_write_section_creates_a_new_file(tmp_path, monkeypatch):
    monkeypatch.setattr(core, "_verilator_version", lambda: "5.034")
    doc = core.write_section(tmp_path / "new.json", [])
    assert doc["schema_version"] == 1 and doc["autofix"]["attempts"] == []


def test_finish_rows_sets_verified_only_when_lint_ok_and_pass():
    def row(ok):
        return {"verified": False, "_lint_ok": ok}
    rows = [row(True), row(False)]
    core._finish_rows(rows, "PASS")
    assert [r["verified"] for r in rows] == [True, False]
    rows = [row(True)]
    core._finish_rows(rows, "FAIL")
    assert rows[0]["verified"] is False and "FAIL" in rows[0]["note"]
    rows = [row(True)]
    core._finish_rows(rows, None)
    assert rows[0]["verified"] is False and "not run" in rows[0]["note"]


@needs_verilator
@pytest.mark.parametrize("design", ["fifo", "spi", "timer"])
def test_all_rules_clear_their_warnings(design, tmp_path):
    res = core.fix_design({"name": design}, EXAMPLES, tmp_path, core.all_rules())
    assert res["status"] == "kept"
    for rule in ("BLKSEQ", "BLKANDNBLK", "COMBDLY", "CASEINCOMPLETE"):
        assert rule not in res["rules_after"]
    # nothing new appeared
    assert set(res["rules_after"]) <= set(res["rules_before"])
    rules_done = {a["rule"] for a in res["attempts"]}
    assert rules_done == {"BLKSEQ", "COMBDLY", "CASEINCOMPLETE"}
    for a in res["attempts"]:
        assert ROW_KEYS <= a.keys()
        assert "_lint_ok" not in a
        assert a["file"] == f"examples/{design}/buggy/{design}.v" or a["file"].endswith(f"buggy/{design}.v")
        assert a["verified"] is False  # regression was not run


@needs_verilator
def test_original_file_is_not_modified(tmp_path):
    src = EXAMPLES / "fifo" / "buggy" / "fifo.v"
    before = src.read_bytes()
    core.fix_design({"name": "fifo"}, EXAMPLES, tmp_path, [combdly, caseincomplete, blkseq])
    assert src.read_bytes() == before
    assert not (tmp_path / "fifo" / "_cur").exists()
