# autofix

Deterministic fixes for Verilator lint warnings in `examples/*/buggy`. Each fix is applied
to a copy, re-linted, and the testbench is run before and after it. A fix is kept only if it
is verified. The original files are never edited.

## Rules

| Rule | Fix |
| --- | --- |
| `BLKSEQ` (clears `BLKANDNBLK`) | `=` becomes `<=` on the flagged line in a clocked block |
| `COMBDLY` | `<=` becomes `=` on the flagged line in a combinational block |
| `CASEINCOMPLETE` | adds a `default` before the matching `endcase`: `default: ;` in a clocked block (registers hold their value), `default: <var> = '0;` in a combinational block |

Each rule is one module (`blkseq.py`, `combdly.py`, `caseincomplete.py`) with `RULES`,
`CLEARED_RULES` and a pure `fix_source(text, lines)`. The shared loop is in `core.py`.
Rules run in that order, and later rules see the earlier fixes.

## What `verified` means

A fix is `verified` when all of these hold:

1. the targeted warning is gone,
2. no new warning appears,
3. the design builds with its testbench, and
4. the testbench result is **no worse than before that fix**
   (`NOT BUILDABLE` < `FAIL` = `TIMEOUT` < `PASS`).

A fix that is not verified is not kept. Each row records `regression_before` and
`regression_after` (see `docs/results_schema.md`).

The planted-bug examples feed every planted-bug signal into their `empty` output, so their
testbenches do not print PASS until every planted bug is fixed. Verified therefore means
"did not make things worse", not "the testbench passes". For example, BLKSEQ turns the buggy
FIFO from `NOT BUILDABLE` into `FAIL`, which is an improvement.

## Run

Use the MSYS2 UCRT64 terminal with Verilator 5.034 (see `docs/windows_setup.md`).

    python -m autofix                                  # fix all designs, write to results/autofix/
    python -m autofix --results results/results.json   # also write the autofix section
    python -m autofix --no-regress                     # skip the testbench (fast; nothing is verified)
    python -m autofix --require-pass                   # strict: delete the fixed file unless the
                                                       # final testbench prints PASS

Regression runs by default, so a run builds each design a few times and takes longer than lint.

## Output

Rows follow `docs/results_schema.md` (`autofix.attempts`): `design`, `rule`, `file`, `line`,
`before`, `after`, `verified`, `note`, plus the extra fields `regression_before` and
`regression_after`.

## Tests

    python -m pytest autofix

The engine tests use a stubbed linter and testbench, so they run without Verilator. The
tests on the real examples are skipped when Verilator is not found.
