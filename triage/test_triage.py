"""Test suite for the triage tool."""

import json
from pathlib import Path
from tests.test_results_schema import validate
from triage.runner import classify_triage, triage_test, write_triage_section


def test_classify_triage():
    assert classify_triage(5, 5) == "repeatable"
    assert classify_triage(5, 2) == "flaky"
    assert classify_triage(5, 1) == "flaky"
    assert classify_triage(5, 0) == "pass"


def test_write_triage_section(tmp_path):
    out_file = tmp_path / "results.json"
    initial_doc = {
        "schema_version": 1,
        "run": {"id": "test-run", "started_at": "2026-11-17T00:00:00Z", "verilator_version": "5.034"},
        "regression": {"generated_at": "2026-11-17T00:00:00Z", "tests": []},
    }
    out_file.write_text(json.dumps(initial_doc))

    labels = [{"design": "fifo", "test": "tb_fifo", "label": "repeatable", "runs": 5, "failures": 5}]
    doc = write_triage_section(out_file, labels, "5.034")

    # Assert existing sections preserved
    assert "regression" in doc
    assert "triage" in doc
    assert doc["triage"]["labels"][0]["label"] == "repeatable"

    # Validate schema
    errors = validate(doc)
    assert not errors, f"Schema validation errors: {errors}"


def test_triage_flaky_testbench(tmp_path):
    out_file = tmp_path / "results.json"
    res = triage_test(
        design="fifo",
        test_name="tb_fifo_flaky",
        variant="golden",
        seeds=[1, 2, 3, 4, 5],
        out_path=out_file,
    )

    assert res["design"] == "fifo"
    assert res["test"] == "tb_fifo_flaky"
    assert res["label"] == "flaky"
    assert res["runs"] == 5
    assert 0 < res["failures"] < 5

    doc = json.loads(out_file.read_text())
    assert not validate(doc)


def test_write_triage_section_corrupt_file_raises(tmp_path):
    import pytest
    out_file = tmp_path / "results.json"
    out_file.write_text("{ this is corrupt json", encoding="utf-8")

    labels = [{"design": "fifo", "test": "tb_fifo", "label": "repeatable", "runs": 5, "failures": 5}]
    with pytest.raises(RuntimeError, match="Cannot update corrupt"):
        write_triage_section(out_file, labels, "5.034")


def test_passing_test_is_not_written(tmp_path):
    out_file = tmp_path / "results.json"
    labels = [{"design": "fifo", "test": "tb_fifo", "label": "pass", "runs": 3, "failures": 0}]
    doc = write_triage_section(out_file, labels, "5.034")
    assert doc["triage"]["labels"] == []
    assert not validate(doc)


def test_passing_test_removes_its_stale_failure(tmp_path):
    out_file = tmp_path / "results.json"
    failing = {"design": "fifo", "test": "tb_fifo", "label": "repeatable", "runs": 3, "failures": 3}
    other = {"design": "spi", "test": "tb_spi", "label": "flaky", "runs": 3, "failures": 1}
    write_triage_section(out_file, [failing, other], "5.034")
    fixed = dict(failing, label="pass", failures=0)
    doc = write_triage_section(out_file, [fixed], "5.034")
    assert [l["design"] for l in doc["triage"]["labels"]] == ["spi"]
    assert not validate(doc)


def test_triage_repeatable_testbench(tmp_path):
    out_file = tmp_path / "results.json"
    res = triage_test(
        design="fifo",
        test_name="tb_fifo_repeatable",
        variant="golden",
        seeds=[1, 2, 3, 4, 5],
        out_path=out_file,
    )

    assert res["test"] == "tb_fifo_repeatable"
    assert res["label"] == "repeatable"
    assert res["runs"] == 5
    assert res["failures"] == 5

    doc = json.loads(out_file.read_text())
    assert doc["triage"]["labels"] == [res]
    assert not validate(doc)
