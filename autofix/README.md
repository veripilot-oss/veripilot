# autofix

Deterministic fixes for Verilator lint warnings in `examples/*/buggy`. Each fix is applied
to a copy, re-linted, and the testbench is run before and after it. A fix is kept only if it
is lint clean and no worse. The original files are never edited.

## Rules

| Rule | Fix |
| --- | --- |
| `BLKSEQ` (clears `BLKANDNBLK`) | `=` becomes `<=` on the flagged line in a clocked block |
| `COMBDLY` | `<=` becomes `=` on the flagged line in a combinational block |
| `CASEINCOMPLETE` | adds a `default` before the matching `endcase`: `default: ;` in a clocked block (registers hold their value), `default: <var> = '0;` in a combinational block |
| `LATCH` | adds `<signal> = '0;` as the first statement of the `always @(*) begin` block; skipped if the block assigns several signals, uses a select, or already has a default |
| `WIDTHEXPAND` | widens narrow sized literals to the target width, e.g. `8'hA5` becomes `16'h00A5` |
| `WIDTHTRUNC` | slices a wider plain identifier RHS to the target width, e.g. `write[3:0]` |
| `UNUSEDSIGNAL` | deletes an unused one-name internal `reg`/`wire`/`logic` declaration; ports and partly used signals are skipped |
| `UNDRIVEN` | ties an undriven internal `wire` to zero (`wire x = 1'b0;`) or adds `assign x = 1'b0;` for an `output wire`; `reg` and `output reg` are skipped |

Each rule is one module (`blkseq.py`, `combdly.py`, `caseincomplete.py`, `latch.py`, `widthexpand.py`, `widthtrunc.py`, `undriven.py`, `unusedsignal.py`) with `RULES`,
`CLEARED_RULES` and a pure `fix_source(text, lines)`. The shared loop is in `core.py`.
Rules run in that order, and later rules see the earlier fixes.

## What `verified` means

A fix is `verified` only when all of these hold:

1. the targeted warning is gone,
2. no new warning appears,
3. the design builds with its testbench, and
4. the testbench ends in `PASS`.

A fix that is lint clean and builds, and whose testbench is no worse than before
(`NOT BUILDABLE` < `FAIL` = `TIMEOUT` < `PASS`), is **kept** so later fixes can build on it,
but it is not verified until the testbench passes. A fix that makes the testbench worse, or
breaks the build, is reverted. Each row records `regression_before` and `regression_after`
(see `docs/results_schema.md`).

The planted-bug examples do not print PASS until every planted bug is fixed, and autofix covers
only some of them. On the buggy examples, `verified` is therefore `false` for every row. The
`note` says what happened, for example BLKSEQ turns the buggy FIFO from `NOT BUILDABLE` into
`FAIL`: kept as progress, not verified.

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
