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


def test_judge_verified_needs_lint_build_and_no_worse_testbench():
    j = core._judge
    assert j(True, True, "NOT BUILDABLE", "FAIL")[0] is True      # now builds: better
    assert j(True, True, "FAIL", "FAIL")[0] is True               # no worse
    assert j(True, True, "FAIL", "PASS")[0] is True
    assert j(True, True, "PASS", "PASS")[0] is True
    assert j(True, True, "PASS", "FAIL")[0] is False              # got worse
    assert j(True, True, "FAIL", "NOT BUILDABLE")[0] is False     # broke the build
    assert j(True, True, "NOT BUILDABLE", "NOT BUILDABLE")[0] is False
    assert j(False, True, "FAIL", None)[0] is False               # lint did not clear
    verified, note = j(True, False, None, None)                   # --no-regress
    assert verified is False and "not run" in note


def test_judge_timeout_and_fail_rank_equal():
    assert core._judge(True, True, "FAIL", "TIMEOUT")[0] is True
    assert core._judge(True, True, "TIMEOUT", "FAIL")[0] is True


# --- engine with a stubbed testbench and a stubbed linter (no Verilator needed) ---------------

_NL = chr(10)


class _Rule:
    """Tiny rule: replaces the word BAD with GOOD on flagged lines."""
    RULES = {"X"}
    CLEARED_RULES = {"X"}

    @staticmethod
    def fix_source(text, lines):
        src = text.split(_NL)
        done = []
        for n in lines:
            if "BAD" in src[n - 1]:
                src[n - 1] = src[n - 1].replace("BAD", "GOOD")
                done.append(n)
        return _NL.join(src), done


def _make_example(tmp_path):
    ex = tmp_path / "examples" / "d" / "buggy"
    ex.mkdir(parents=True)
    (ex / "d.v").write_text(_NL.join(["a", "BAD", "c", ""]), encoding="utf-8")
    (tmp_path / "examples" / "d" / "tb_d.v").write_text("// tb" + _NL, encoding="utf-8")
    return tmp_path / "examples"


def _stub(monkeypatch, tb_results, lint_clears=True):
    """lint: flags X on every line containing BAD. testbench: pops results in order."""
    def fake_lint(path):
        text = Path(path).read_text(encoding="utf-8").split(_NL)
        return [("X", i + 1) for i, ln in enumerate(text) if "BAD" in ln]

    def fake_lint_text(text, workdir, name):
        lines = text.split(_NL)
        flagged = [("X", i + 1) for i, ln in enumerate(lines) if "BAD" in ln]
        return flagged if lint_clears or "GOOD" not in text else [("X", 2)]

    seq = list(tb_results)
    monkeypatch.setattr(core, "lint", fake_lint)
    monkeypatch.setattr(core, "lint_text", fake_lint_text)
    monkeypatch.setattr(core, "run_testbench", lambda *a, **k: seq.pop(0))
    return seq


def test_verified_row_records_before_and_after(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    _stub(monkeypatch, ["NOT BUILDABLE", "FAIL"])               # baseline, after the fix
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule])
    row = res["attempts"][0]
    assert row["verified"] is True
    assert row["regression_before"] == "NOT BUILDABLE"
    assert row["regression_after"] == "FAIL"
    assert res["status"] == "kept" and res["testbench"] == "FAIL"
    assert "GOOD" in (tmp_path / "out" / "d" / "d.v").read_text()


def test_fix_that_makes_the_testbench_worse_is_not_verified_or_kept(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    _stub(monkeypatch, ["PASS", "FAIL"])
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule])
    row = res["attempts"][0]
    assert row["verified"] is False
    assert row["regression_before"] == "PASS" and row["regression_after"] == "FAIL"
    assert "worse" in row["note"]
    assert res["status"] == "reverted"
    assert not (tmp_path / "out" / "d" / "d.v").exists()


def test_fix_that_breaks_the_build_is_not_verified(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    _stub(monkeypatch, ["FAIL", "NOT BUILDABLE"])
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule])
    assert res["attempts"][0]["verified"] is False
    assert res["status"] == "reverted"


def test_lint_failure_skips_the_testbench_and_omits_regression_after(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    seq = _stub(monkeypatch, ["FAIL"], lint_clears=False)       # only the baseline run is allowed
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule])
    row = res["attempts"][0]
    assert row["verified"] is False
    assert row["regression_before"] == "FAIL" and "regression_after" not in row
    assert seq == []


def test_no_regress_keeps_a_lint_clean_fix_but_never_verifies_it(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    _stub(monkeypatch, [])                                      # any testbench call would raise
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule], regress=False)
    row = res["attempts"][0]
    assert row["verified"] is False and "regression_before" not in row
    assert res["status"] == "kept" and "testbench" not in res


def test_require_pass_is_strict(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    _stub(monkeypatch, ["NOT BUILDABLE", "FAIL"])
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule], require_pass=True)
    assert res["attempts"][0]["verified"] is True               # per-fix rule is unchanged
    assert res["status"] == "reverted"                          # but the final result is not PASS
    assert not (tmp_path / "out" / "d" / "d.v").exists()


def test_require_pass_keeps_file_when_final_testbench_passes(tmp_path, monkeypatch):
    ex = _make_example(tmp_path)
    _stub(monkeypatch, ["FAIL", "PASS"])
    res = core.fix_design({"name": "d"}, ex, tmp_path / "out", [_Rule], require_pass=True)
    assert res["status"] == "kept"
    assert (tmp_path / "out" / "d" / "d.v").exists()


@needs_verilator
@pytest.mark.parametrize("design", ["fifo", "spi", "timer"])
def test_all_rules_clear_their_warnings(design, tmp_path):
    res = core.fix_design({"name": design}, EXAMPLES, tmp_path, core.all_rules(), regress=False)
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
        assert "regression_before" not in a


@needs_verilator
def test_original_file_is_not_modified(tmp_path):
    src = EXAMPLES / "fifo" / "buggy" / "fifo.v"
    before = src.read_bytes()
    core.fix_design({"name": "fifo"}, EXAMPLES, tmp_path, [combdly, caseincomplete, blkseq])
    assert src.read_bytes() == before
    assert not (tmp_path / "fifo" / "_cur").exists()


@needs_verilator
@pytest.mark.parametrize("design", ["fifo", "spi", "timer"])
def test_real_designs_with_regression(design, tmp_path):
    res = core.fix_design({"name": design}, EXAMPLES, tmp_path, core.all_rules())
    assert res["status"] == "kept"
    assert res["testbench"] in ("FAIL", "PASS")        # the fixed design builds
    for a in res["attempts"]:
        assert a["regression_before"] in core.TB_RANK
        assert a["regression_after"] in core.TB_RANK
        assert a["verified"] is True
        assert core.TB_RANK[a["regression_after"]] >= core.TB_RANK[a["regression_before"]]
    # BLKSEQ is what lets the buggy design build at all
    first = next(a for a in res["attempts"] if a["rule"] == "BLKSEQ")
    assert first["regression_before"] == "NOT BUILDABLE" and first["regression_after"] != "NOT BUILDABLE"
