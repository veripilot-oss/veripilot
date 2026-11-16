"""Unit tests for the health score."""

import json
import sys
from pathlib import Path

import pytest

from health.score import (autofix_score, compute_health, coverage_score,
                          lint_score, regression_score)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))
from test_results_schema import validate  # noqa: E402


def test_lint_penalties_and_floor():
    assert lint_score({"warnings": []}) == 100
    w = [{"severity": "warning"}] * 3 + [{"severity": "error"}]
    assert lint_score({"warnings": w}) == 100 - 3 * 2 - 10
    assert lint_score({"warnings": [{"severity": "error"}] * 20}) == 0
    assert lint_score({}) is None


def test_regression_pass_rate():
    tests = [{"status": "pass"}, {"status": "fail"}, {"status": "pass"}, {"status": "pass"}]
    assert regression_score({"tests": tests}) == 75
    assert regression_score({"tests": []}) is None


def test_coverage_ignores_null_toggle():
    s = {"designs": [{"line_percent": 80, "toggle_percent": None},
                     {"line_percent": 60, "toggle_percent": 40}]}
    assert coverage_score(s) == pytest.approx(60)
    assert coverage_score({"designs": [{"line_percent": 50, "toggle_percent": None}]}) == 50
    assert coverage_score({"designs": []}) is None


def test_autofix_only_counts_verified_true():
    a = [{"verified": True}, {"verified": False}, {"verified": True}, {"verified": False}]
    assert autofix_score({"attempts": a}) == 50
    assert autofix_score({"attempts": []}) is None


def test_nothing_measurable_returns_none():
    assert compute_health({}) is None
    assert compute_health({"regression": {"tests": []}, "autofix": {"attempts": []}}) is None


def test_weights_rescale_when_sections_missing():
    # Only regression present: its score is the overall score.
    doc = {"regression": {"tests": [{"status": "pass"}, {"status": "fail"}]}}
    assert compute_health(doc) == {"score": 50.0, "components": {"regression": 50.0}}


def test_all_perfect_is_100_and_all_bad_is_0():
    good = {
        "lint": {"warnings": []},
        "regression": {"tests": [{"status": "pass"}]},
        "coverage": {"designs": [{"line_percent": 100, "toggle_percent": 100}]},
        "autofix": {"attempts": [{"verified": True}]},
    }
    assert compute_health(good)["score"] == 100.0
    bad = {
        "lint": {"warnings": [{"severity": "error"}] * 10},
        "regression": {"tests": [{"status": "fail"}]},
        "coverage": {"designs": [{"line_percent": 0, "toggle_percent": 0}]},
        "autofix": {"attempts": [{"verified": False}]},
    }
    assert compute_health(bad)["score"] == 0.0


def test_score_is_within_range_and_monotonic_in_regression():
    def doc(passes):
        return {"regression": {"tests": [{"status": "pass"}] * passes + [{"status": "fail"}] * (4 - passes)},
                "lint": {"warnings": [{"severity": "warning"}] * 5}}
    scores = [compute_health(doc(p))["score"] for p in range(5)]
    assert scores == sorted(scores)
    assert all(0 <= s <= 100 for s in scores)


def test_example_health_matches_function():
    doc = json.loads((ROOT / "examples" / "results.example.json").read_text())
    expected = compute_health(doc)
    assert doc["health"]["score"] == expected["score"]
    assert doc["health"]["components"] == expected["components"]
    doc["health"].update(expected)
    assert validate(doc) == []
