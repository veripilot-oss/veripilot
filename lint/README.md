# lint

Runs Verilator lint on the `buggy/` version of each example design, checks the result against the planted bugs in `bugs.yaml`, and writes two files.

## Usage

Run from the repository root with `PYTHONPATH=.` set:

```
$ python3 lint/linter.py examples results/lint.json
Lint complete: 42/42 planted bugs detected across 3 design(s).
Results saved to results/lint.json
Updated lint section in results/results.json
```

```
python3 lint/linter.py [examples_dir] [lint.json] [results.json]
```

| Argument | Default | Meaning |
| --- | --- | --- |
| `examples_dir` | `examples` | Folder with one subfolder per design. A design is used if it has `buggy/<name>.v`. |
| `lint.json` | `results/lint.json` | Detailed output. Autofix reads this file. |
| `results.json` | `results.json` next to `lint.json` | The shared results file. Only its `lint` section is changed. |

Verilator runs as `verilator --lint-only -Wall`. Use Verilator 5.034.

## What it writes

**`results/lint.json`** has one entry per design with its findings, how many planted bugs there are, how many were detected, the ids of any that were missed, and the number of extra findings. This file is rewritten on every run.

**`results/results.json`** gets a `lint` section as described in `docs/results_schema.md`:

```json
{
  "lint": {
    "generated_at": "2026-11-18T00:00:00Z",
    "warnings": [
      {
        "design": "fifo",
        "rule": "PINMISSING",
        "file": "examples/fifo/buggy/fifo.v",
        "line": 90,
        "severity": "warning",
        "message": "Cell has missing pin: 'parity_err'",
        "matched_bug_id": 13
      }
    ]
  }
}
```

- Every finding is listed, including ones that match no planted bug (`matched_bug_id` is `null`).
- `file` is relative to the repository, with forward slashes.
- Other sections are left untouched. A missing results file is created. An existing section named `lint` is replaced.
- If the results file exists but is not valid JSON, the command prints an error, exits with code 1 and does not change the file. `lint.json` is still written.

## How a planted bug counts as detected

A planted bug in `bugs.yaml` is detected when Verilator reports the **same rule on the same line**. The `Lint complete` line counts those.

## Effect on the health score

The health score treats each warning as a 2 point penalty (10 for an error) and floors at 0. The examples are buggy on purpose, so `python -m health` gives lint a score of 0 after this runs. That is expected, not a failure.

## Tests

```
python3 -m pytest lint
```

`test_lint.py` checks detection counts. `test_results_section.py` checks the schema format, that other sections are preserved, and that a corrupt file is rejected.
