"""Health score: one 0-100 number computed from a results.json document.

Each stage that has results gives a component score (0-100, higher is better):

    lint        100 - 10 per error - 2 per warning, floored at 0
    regression  percent of test runs that passed
    coverage    mean of every line_percent and non-null toggle_percent
    autofix     percent of fix attempts that were verified

The overall score is the weighted mean of the components that can be measured.
A section that is missing, or has nothing to measure (no tests, no attempts, no
designs), is left out and the remaining weights are rescaled. An empty lint
warning list counts as clean (100). With nothing measurable, the result is None
and the caller should omit the `health` section.

See docs/results_schema.md.
"""

from __future__ import annotations

from typing import Optional

WEIGHTS = {"regression": 0.40, "coverage": 0.25, "lint": 0.25, "autofix": 0.10}
ERROR_PENALTY = 10.0
WARNING_PENALTY = 2.0


def _clamp(x: float) -> float:
    return max(0.0, min(100.0, x))


def lint_score(section: dict) -> Optional[float]:
    warnings = section.get("warnings")
    if warnings is None:
        return None
    errors = sum(1 for w in warnings if w.get("severity") == "error")
    others = len(warnings) - errors
    return _clamp(100.0 - ERROR_PENALTY * errors - WARNING_PENALTY * others)


def regression_score(section: dict) -> Optional[float]:
    tests = section.get("tests") or []
    if not tests:
        return None
    return 100.0 * sum(1 for t in tests if t.get("status") == "pass") / len(tests)


def coverage_score(section: dict) -> Optional[float]:
    values = []
    for d in section.get("designs") or []:
        for key in ("line_percent", "toggle_percent"):
            if d.get(key) is not None:
                values.append(d[key])
    if not values:
        return None
    return _clamp(sum(values) / len(values))


def autofix_score(section: dict) -> Optional[float]:
    attempts = section.get("attempts") or []
    if not attempts:
        return None
    return 100.0 * sum(1 for a in attempts if a.get("verified") is True) / len(attempts)


_SCORERS = {
    "regression": regression_score,
    "coverage": coverage_score,
    "lint": lint_score,
    "autofix": autofix_score,
}


def compute_health(results: dict) -> Optional[dict]:
    """Return {"score": float, "components": {...}} or None if nothing is measurable.

    The caller adds `generated_at` and stores the dict as results["health"].
    """
    components = {}
    for name, scorer in _SCORERS.items():
        section = results.get(name)
        if isinstance(section, dict):
            value = scorer(section)
            if value is not None:
                components[name] = value
    if not components:
        return None
    total = sum(WEIGHTS[n] for n in components)
    score = sum(WEIGHTS[n] * v for n, v in components.items()) / total
    return {
        "score": round(score, 1),
        "components": {n: round(v, 1) for n, v in components.items()},
    }
