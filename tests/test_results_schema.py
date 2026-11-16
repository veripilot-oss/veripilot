"""Validate examples/results.example.json against docs/results_schema.md.

Stdlib only, so it runs without extra dependencies. Keep in step with the doc.
"""

import json
import re
from pathlib import Path

import pytest

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "results.example.json"
TS = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
SECTIONS = {"lint", "autofix", "regression", "coverage", "triage", "health"}


def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _pct(v):
    return _is_num(v) and 0 <= v <= 100


def _is_str(v):
    return isinstance(v, str)


# field -> (check, required)
ROWS = {
    "lint": ("warnings", {
        "design": (_is_str, True), "rule": (_is_str, True), "file": (_is_str, True),
        "line": (lambda v: _is_int(v) and v >= 1, True),
        "severity": (lambda v: v in ("warning", "error"), True),
        "message": (_is_str, True),
        "matched_bug_id": (lambda v: v is None or _is_int(v), False),
    }),
    "autofix": ("attempts", {
        "design": (_is_str, True), "rule": (_is_str, True), "file": (_is_str, True),
        "line": (lambda v: _is_int(v) and v >= 1, True),
        "before": (_is_str, True), "after": (_is_str, True),
        "verified": (lambda v: isinstance(v, bool), True),
        "note": (_is_str, False),
    }),
    "regression": ("tests", {
        "design": (_is_str, True), "test": (_is_str, True),
        "status": (lambda v: v in ("pass", "fail"), True),
        "seed": (_is_int, True),
        "duration_s": (lambda v: _is_num(v) and v >= 0, True),
    }),
    "coverage": ("designs", {
        "design": (_is_str, True),
        "line_percent": (_pct, True),
        "toggle_percent": (lambda v: v is None or _pct(v), True),
    }),
    "triage": ("labels", {
        "design": (_is_str, True), "test": (_is_str, True),
        "label": (lambda v: v in ("flaky", "repeatable"), True),
        "runs": (lambda v: _is_int(v) and v >= 1, False),
        "failures": (lambda v: _is_int(v) and v >= 0, False),
    }),
}


def validate(doc):
    """Return a list of problems; empty means valid."""
    errs = []
    if not isinstance(doc, dict):
        return ["top level must be an object"]
    if doc.get("schema_version") != 1 or not _is_int(doc.get("schema_version")):
        errs.append("schema_version must be 1")
    run = doc.get("run")
    if not isinstance(run, dict):
        errs.append("run is required")
    else:
        for k in ("id", "verilator_version"):
            if not _is_str(run.get(k)):
                errs.append(f"run.{k} must be a string")
        if not (_is_str(run.get("started_at")) and TS.match(run["started_at"])):
            errs.append("run.started_at must be UTC ISO 8601")
    for name in SECTIONS & doc.keys():
        sec = doc[name]
        if not isinstance(sec, dict):
            errs.append(f"{name} must be an object")
            continue
        if not (_is_str(sec.get("generated_at")) and TS.match(sec["generated_at"])):
            errs.append(f"{name}.generated_at must be UTC ISO 8601")
        if name in ROWS:
            key, fields = ROWS[name]
            rows = sec.get(key)
            if not isinstance(rows, list):
                errs.append(f"{name}.{key} must be a list")
                continue
            for i, row in enumerate(rows):
                for f, (check, required) in fields.items():
                    if f not in row:
                        if required:
                            errs.append(f"{name}.{key}[{i}].{f} is missing")
                    elif not check(row[f]):
                        errs.append(f"{name}.{key}[{i}].{f} invalid: {row[f]!r}")
        else:  # health
            if not _pct(sec.get("score")):
                errs.append("health.score must be a number 0-100")
            comps = sec.get("components", {})
            for k, v in comps.items():
                if k not in ("lint", "regression", "coverage", "autofix") or not _pct(v):
                    errs.append(f"health.components.{k} invalid")
    return errs


def load():
    return json.loads(EXAMPLE.read_text(encoding="utf-8"))


def test_example_is_valid():
    assert validate(load()) == []


def test_example_covers_every_section():
    assert SECTIONS <= load().keys()


def test_sections_are_optional():
    doc = load()
    for name in SECTIONS:
        doc.pop(name)
    assert validate(doc) == []


@pytest.mark.parametrize("mutate", [
    lambda d: d.pop("run"),
    lambda d: d.update(schema_version=2),
    lambda d: d["regression"]["tests"][0].update(status="passed"),
    lambda d: d["regression"]["tests"][0].pop("seed"),
    lambda d: d["autofix"]["attempts"][0].update(verified="yes"),
    lambda d: d["coverage"]["designs"][0].update(line_percent=101),
    lambda d: d["triage"]["labels"][0].update(label="unknown"),
    lambda d: d["health"].update(score=-1),
    lambda d: d["lint"].update(generated_at="yesterday"),
])
def test_invalid_documents_are_rejected(mutate):
    doc = load()
    mutate(doc)
    assert validate(doc) != []
