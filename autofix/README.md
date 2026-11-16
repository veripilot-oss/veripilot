# autofix

Deterministic fixes for Verilator lint warnings in `examples/*/buggy`. Each fix is applied
to a copy, re-linted, and kept only if its warnings are gone and no new warning appears.
The original files are never edited.

## Rules

| Rule | Fix |
| --- | --- |
| `BLKSEQ` (clears `BLKANDNBLK`) | `=` becomes `<=` on the flagged line in a clocked block |
| `COMBDLY` | `<=` becomes `=` on the flagged line in a combinational block |
| `CASEINCOMPLETE` | adds `default: <var> = '0;` before the matching `endcase` |

Each rule is one module (`blkseq.py`, `combdly.py`, `caseincomplete.py`) with `RULES`,
`CLEARED_RULES` and a pure `fix_source(text, lines)`. The shared loop is in `core.py`.
Rules run in that order, and later rules see the earlier fixes.

## Run

Use the MSYS2 UCRT64 terminal with Verilator 5.034 (see `docs/windows_setup.md`).

    python -m autofix                              # fix all designs, write to results/autofix/
    python -m autofix --results results/results.json   # also write the autofix section
    python -m autofix --regress                    # also run each testbench on the fixed design

`--require-pass` additionally deletes the fixed file unless the testbench prints PASS.

## Output

Rows follow `docs/results_schema.md` (`autofix.attempts`): `design`, `rule`, `file`, `line`,
`before`, `after`, `verified`, `note`. `verified` is true only if lint is clean for the
warning **and** the testbench prints PASS (needs `--regress`).

## Limits

The buggy examples feed every planted-bug signal into their `empty` output, so their
testbenches fail until all of those signals are fixed. With only these three rules,
`verified` stays false and the note says so. Run `python -m pytest autofix` to test.
