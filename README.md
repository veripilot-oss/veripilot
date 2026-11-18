# VeriPilot

Your co-pilot for chip verification. An open-source pipeline that lints an RTL design, tries safe fixes, runs the tests with several seeds, measures coverage, labels flaky failures, and shows one health score on a dashboard.

The rule behind it: **a tool may suggest, the simulator decides.** A fix only counts as verified if the checks still hold afterwards.

## What it does

```
lint → autofix → regression → coverage → triage → health score → dashboard
```

Every stage writes only its own section of `results/results.json`. The dashboard reads that one file. The format is in [docs/results_schema.md](docs/results_schema.md).

| Stage | Folder | What it does |
| --- | --- | --- |
| Lint | `lint/` | Runs Verilator lint and checks it finds the bugs planted in each example. |
| Autofix | `autofix/` | Applies safe fixes for `BLKSEQ`, `COMBDLY` and `CASEINCOMPLETE` to a copy, then re-lints and re-runs the testbench. |
| Regression | `regress/` | Builds a testbench with Verilator and runs it for each seed. |
| Coverage | `coverage_advisor/` | Reports line coverage and the lines never reached. |
| Triage | `triage/` | Re-runs a failing test with several seeds: always fails is `repeatable`, sometimes fails is `flaky`. |
| Health | `health/` | Combines the stages into one 0 to 100 score. |
| Dashboard | `dashboard/` | A static page that shows `results.json`. |

Example designs live in `examples/` (`fifo`, `spi`, `timer`). Each has a `golden/` version, a `buggy/` version with planted bugs, a testbench, and a `bugs.yaml` answer key.

## What it can and cannot catch

Lint finds **structural** mistakes without any testbench: a signal never driven, a width mismatch, a missing `case` branch, a latch. It cannot know what your design is *supposed* to do. A clean adder that subtracts instead of adds passes lint. For that you need tests, and coverage tells you where your tests are weak.

Not built yet: an LLM that drafts fixes or new test inputs. Autofix is rule-based today and covers only the three rules above.

## Quick start

You need Python 3.10 or newer, `pytest` and `pyyaml`, and **Verilator 5.034 exactly**:

```bash
verilator --version      # must start with: Verilator 5.034
python3 -m pip install pytest pyyaml
```

Windows: use the MSYS2 UCRT64 terminal and follow [docs/windows_setup.md](docs/windows_setup.md).

Run the whole pipeline from the repo root:

```bash
export PYTHONPATH=.

# 1. regression on each design (creates results/results.json)
for d in fifo spi timer; do python3 -m regress.runner $d --seeds 1 2 3; done

# 2. triage the two demo tests: one flaky, one that fails every time
python3 -m triage.runner fifo --test tb_fifo_flaky --seeds 1 2 3 4 5
python3 -m triage.runner fifo --test tb_fifo_repeatable --seeds 1 2 3 4 5

# 3. lint the buggy examples
python3 lint/linter.py examples results/lint.json

# 4. try safe fixes on the buggy examples
python3 -m autofix --examples examples --results results/results.json

# 5. coverage
python3 coverage_advisor/advisor.py fifo spi timer

# 6. health score
python3 -m health
```

Then serve the repo and open the dashboard:

```bash
python3 -m http.server 8000
```

Open <http://localhost:8000/dashboard/>.

Run the tests with `python3 -m pytest` (about two minutes).

## Known limits

- Lint runs only on the `buggy/` examples, which have 63 warnings by design, so the lint part of the health score is 0. That is expected.
- Autofix marks a fix `verified` when the testbench is *no worse than before*. On a buggy design whose testbench already fails, a fix can be verified while the testbench still fails. See the `note` on each attempt.
- Verilator must be 5.034. Results from another version are not accepted.

## Demo script (about 3 minutes)

1. **The problem.** Open `examples/fifo/buggy/fifo.v`. It has planted bugs and nothing fails when you read it.
2. **Lint.** Run step 3. Say: "42 of 42 planted bugs found, with no testbench."
3. **Autofix.** Run step 4. Open the dashboard and expand `fifo` to show the before and after of a fix.
4. **Flaky versus real.** Run step 2. In the dashboard, the triage column for `fifo` now reads "1 flaky, 1 repeatable": `tb_fifo_flaky` fails on some seeds (flaky, depends on the seed) and `tb_fifo_repeatable` fails on all of them (repeatable, a real bug to fix).
5. **Score.** Run steps 5 and 6, reload, and read the verdict and health score.
6. **Honest close.** "Lint needs no tests. Everything else needs good tests. Coverage shows where yours are weak."

## Fallback plan

- **A stage fails live.** Skip it. A missing stage shows as "not run", never as zero, and the page still works.
- **No `results.json` or the pipeline will not run.** The dashboard falls back to `examples/results.example.json` and shows a banner saying it is example data. Say so out loud.
- **The page will not load.** You opened it as a file, not through the server. Run `python3 -m http.server 8000`, or use **Open results.json** on the page.
- **Verilator is not 5.034.** Stop and fix that first. Do not demo results from another version.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Short version: never push to `main`, open a pull request, one reviewer, and the owner merges.
