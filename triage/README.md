# Triage

Triage reruns one test with several random seeds and labels a failure as `repeatable` or `flaky`. The label is written to `results/results.json` and shown on the dashboard.

Triage works on its own. It does not read lint or regression output, and no other stage reads its label.

---

## Purpose

A test that fails once is not enough information. Triage builds the testbench with Verilator and runs it once per seed:

- **`repeatable`**: it fails on every seed. This points to a genuine logic bug.
- **`flaky`**: it passes on some seeds and fails on others. This points to something that depends on the seed, such as a race, a timing assumption or an uninitialised value.
- **`pass`**: it fails on no seed. Nothing is written for it (see Outputs).

A run counts as passing only if the simulator exits with code 0, prints a line starting with `PASS`, and prints no `FAIL`. A run that exceeds 300 seconds counts as a failure.

---

## Inputs

Triage takes its inputs from the command line, not from `results/lint.json` or the `regression` section.

| Argument | Default | Meaning |
| --- | --- | --- |
| `design` | `fifo` | Design under `examples/`: `fifo`, `spi` or `timer`. |
| `--test` | `tb_<design>` | Testbench file name in `examples/<design>/`, without `.v`. For example `tb_fifo_flaky`. |
| `--variant` | `golden` | `golden` or `buggy`: which RTL in `examples/<design>/` to build the testbench against. |
| `--seeds` | `1 2 3 4 5` | Seeds to run. Each is passed to the simulator as `+verilator+seed+N`, with random reset values. |
| `--out` | `results/results.json` | The file to update. |

Verilator 5.034 is required. With any other version, triage stops with an error.

---

## Outputs

Triage updates only the `triage` section of the results file and keeps all other sections. If the file does not exist it is created. If it exists but is not valid JSON, triage stops with an error and does not touch it.

```json
{
  "triage": {
    "generated_at": "2026-11-17T00:00:00Z",
    "labels": [
      { "design": "fifo", "test": "tb_fifo_flaky", "label": "flaky", "runs": 5, "failures": 2 }
    ]
  }
}
```

- **`label`**: `"flaky"` or `"repeatable"`, as defined in `docs/results_schema.md`.
- **`runs`**: how many seeds were run.
- **`failures`**: how many of them failed.

Each design and test pair has one entry. Running triage again replaces the old entry. A test that now passes is not written, and its earlier failure entry is removed.

Exit codes: `0` on success. `2` on an error such as a build failure, a missing testbench or a wrong Verilator version. In that case no label is written.

---

## Where it fits

```
examples/<design>/<variant>/<design>.v + examples/<design>/<test>.v
                         │
                         ▼
        [ triage: build once, run once per seed ]
                         │
                         ▼
   results.json  ──>  triage.labels  ──>  dashboard
```

- **Dashboard**: shows the label next to the test's per-seed results and counts flaky and repeatable failures in the summary.
- **Autofix** does not read triage output.
- **Health score** does not use triage. It is computed from regression, coverage, lint and autofix only.

---

## Usage

Run from the repository root with `PYTHONPATH=.` set. The output below is real, with the results path shortened (triage prints the full path).

A flaky test. `tb_fifo_flaky` is a deliberately flaky testbench for the demo:

```
$ python -m triage.runner fifo --test tb_fifo_flaky --seeds 1 2 3 4 5
[fifo:tb_fifo_flaky] label=flaky (2/5 failures across seeds [1, 2, 3, 4, 5])
updated triage section in results/results.json
```

A passing test. Nothing is written to `labels`:

```
$ python -m triage.runner fifo --seeds 1 2 3
[fifo:tb_fifo] label=pass (0/3 failures across seeds [1, 2, 3])
updated triage section in results/results.json
```

A test that cannot be built gives an error and no label. This is what all three buggy variants do today: their planted bugs include `BLKANDNBLK` (blocking and non-blocking assignments mixed), which Verilator reports as an error:

```
$ python -m triage.runner spi --variant buggy --seeds 1 2 3
error: Verilator build failed for spi (tb_spi, variant=buggy):
...
```

---

## Status

- [x] Automated multi-seed rerun engine (`triage.runner`, #25).
- [x] Classifier and `results/results.json` writer (#25).
- [x] A passing test is not written to the results (#31).
- [ ] A `repeatable` demo. No example in `examples/` builds and then fails on every seed (the buggy variants do not build), so there is no real `repeatable` output to show. Adding a small always-failing testbench, like `tb_fifo_flaky`, would fix that.
