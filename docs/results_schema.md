# results.json schema (version 1)

One file, `results/results.json`, carries the output of every VeriPilot stage. The dashboard reads only this file.

## Rules for writers

1. A stage writes **only its own section** and leaves the others untouched. Read the file, replace your section, write it back. If the file does not exist, create it with `schema_version` and `run` plus your section.
2. Every section is **optional**. A missing section means "that stage has not run". The dashboard must not treat it as zero.
3. Every section has a `generated_at` timestamp (UTC, ISO 8601, ending in `Z`).
4. Rows that belong to a design carry a `design` field (`fifo`, `spi`, `timer`). Sections are flat lists, so the dashboard can filter without walking a tree.
5. Unknown extra fields are allowed and ignored. Do not rename or retype existing fields without bumping `schema_version`.
6. `file` paths are repo-relative with forward slashes, for example `examples/fifo/buggy/fifo.v`.

## Top level

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `schema_version` | integer | yes | Currently `1`. |
| `run` | object | yes | See below. |
| `lint` | object | no | Lint warnings. |
| `autofix` | object | no | Fix attempts. |
| `regression` | object | no | Test results. |
| `coverage` | object | no | Coverage per design. |
| `triage` | object | no | Failure labels. |
| `health` | object | no | Overall score. |

### `run`

| Field | Type | Notes |
| --- | --- | --- |
| `id` | string | Unique run id. |
| `started_at` | string | UTC ISO 8601. |
| `verilator_version` | string | Must be `5.034` for results the team accepts. |
| `git_sha` | string | Optional. Commit the run was made from. |

### `lint`

`{ "generated_at": ..., "warnings": [ ... ] }`

| Field | Type | Notes |
| --- | --- | --- |
| `design` | string | |
| `rule` | string | Verilator rule, for example `WIDTHTRUNC`. |
| `file` | string | |
| `line` | integer | 1-based. |
| `severity` | string | `warning` or `error`. |
| `message` | string | |
| `matched_bug_id` | integer or null | Planted bug from `bugs.yaml`, if any. Optional. |

### `autofix`

`{ "generated_at": ..., "attempts": [ ... ] }`

| Field | Type | Notes |
| --- | --- | --- |
| `design` | string | |
| `rule` | string | Warning being fixed. |
| `file` | string | |
| `line` | integer | Line of the original warning. |
| `before` | string | Original code. |
| `after` | string | Proposed code. |
| `verified` | boolean | `true` only if lint is clean for that warning **and** regression still passes. |
| `note` | string | Optional. Why it was or was not verified. |

### `regression`

`{ "generated_at": ..., "tests": [ ... ] }`

| Field | Type | Notes |
| --- | --- | --- |
| `design` | string | |
| `test` | string | Test name, for example `tb_fifo`. |
| `status` | string | `pass` or `fail`. |
| `seed` | integer | Seed used. Needed to reproduce. |
| `duration_s` | number | Wall time in seconds, 0 or more. |

The same test may appear several times with different seeds.

### `coverage`

`{ "generated_at": ..., "designs": [ ... ] }`

| Field | Type | Notes |
| --- | --- | --- |
| `design` | string | |
| `line_percent` | number | 0 to 100. |
| `toggle_percent` | number or null | 0 to 100. `null` when toggle coverage was not collected. |

### `triage`

`{ "generated_at": ..., "labels": [ ... ] }`

| Field | Type | Notes |
| --- | --- | --- |
| `design` | string | |
| `test` | string | A failing test. |
| `label` | string | `flaky` (fails only for some seeds or reruns) or `repeatable` (fails every time). |
| `runs` | integer | Optional. Reruns used to decide. |
| `failures` | integer | Optional. How many of those reruns failed. |

### `health`

`{ "generated_at": ..., "score": ..., "components": { ... } }`

| Field | Type | Notes |
| --- | --- | --- |
| `score` | number | 0 to 100. Higher is healthier. |
| `components` | object | Optional. Sub-scores, each 0 to 100, keyed by `lint`, `regression`, `coverage`, `autofix`. |

## Example

See `examples/results.example.json`. It is validated by `tests/test_results_schema.py`.
