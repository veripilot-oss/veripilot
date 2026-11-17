# Triage

The triage module classifies test failures from simulation runs to distinguish between deterministic bugs and intermittent issues before they are passed down to autofix or reported on the dashboard.

> **Note:** Triage does not filter or alter lint diagnostics. Its focus is characterizing testbench/simulation failures.

---

## Purpose

When a test fails during regression, triage reruns the failing test multiple times across different random seeds:
- **`repeatable`**: The test fails across all reruns (deterministic failure / genuine logic bug).
- **`flaky`**: The test produces mixed results depending on the seed or run (intermittent timing, race condition, or uninitialized state).

This distinction prevents autofix from wasting iterations trying to deterministically patch intermittent test failures and provides high-signal health metrics for the dashboard.

---

## Inputs

- **`results/lint.json`** *(current lint results format)*: Carries static diagnostic findings.
- **`results/results.json`** *(unified schema, see `docs/results_schema.md`)*:
  - Reads the `regression` section containing failing test records (`design`, `test`, `status: "fail"`, `seed`).

---

## Outputs

Triage records its classification under the `triage` section of `results/results.json`:

```json
{
  "triage": {
    "generated_at": "2026-11-17T00:00:00Z",
    "labels": [
      {
        "design": "fifo",
        "test": "tb_fifo",
        "label": "repeatable",
        "runs": 5,
        "failures": 5
      }
    ]
  }
}
```

- **`label`**: `"repeatable"` if all reruns fail; `"flaky"` if results differ across seeds.
- **`runs`**: Total number of evaluation reruns executed.
- **`failures`**: Number of reruns that resulted in failure.

---

## Integration in VeriPilot Pipeline

```
[ Regression Tests ]
         │
         ▼
[ Failing Test Cases ] ──> [ Triage Reruns (Multi-Seed) ]
                                      │
                         ┌────────────┴────────────┐
                         ▼                         ▼
                  "repeatable"                  "flaky"
                         │                         │
                         ▼                         ▼
                  [ Autofix Stage ]       [ Dashboard Warning ]
```

- **Autofix**: Targets `repeatable` failures with priority, avoiding non-deterministic `flaky` failures.
- **Dashboard**: Displays triage status badges next to failing tests and feeds into the overall project health score.

---

## Status & Roadmap

- [x] Documentation & architecture specification (*this document*).
- [x] Automated multi-seed test rerun engine (`triage.runner`).
- [x] Results classifier and `results/results.json` writer.
