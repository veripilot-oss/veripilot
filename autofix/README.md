# autofix/

Iterative lint-fixing tool. Applies deterministic source transforms
to clean up Verilator lint warnings, then runs the testbench in a
sandbox to prove the fix preserves semantics.

A transform is accepted only if:
1. `verilator --lint-only` accepts it with strictly fewer warnings.
2. The fixed file has zero syntax errors.
3. Every testbench for the design still passes under `verilator --trace`.

If any check fails, the change is rolled back. The candidate is kept only if the design
is lint clean and no worse. The original source tree is never modified on disk.

## Supported Rules

| Rule | Action |
| --- | --- |
| `BLKSEQ` | converts blocking assignments (`=`) in sequential `always @(posedge clk)` blocks to non-blocking (`<=`) |
| `COMBDLY` | strips delays (`#N`) from combinational blocks |
| `CASEINCOMPLETE` | synthesizes a defensive `default: ;` or `default: <lhs> = '0;` arm |
| `LATCH` | adds a default assignment at the top of combinational always blocks so all outputs are driven on every path |
| `WIDTHEXPAND` | zero-extends literal RHS values to match LHS target width, e.g. `8'd0` |
| `WIDTHTRUNC` | slices a wider plain identifier RHS to the target width, e.g. `write[3:0]` |
| `UNUSEDSIGNAL` | deletes an unused one-name internal `reg`/`wire`/`logic` declaration; ports and partly used signals are skipped |
| `UNDRIVEN` | ties an undriven internal `wire` to zero (`wire x = 1'b0;`) or adds `assign x = 1'b0;` for an `output wire`; `reg` and `output reg` are skipped |
| `SYNCASYNCNET` | changes asynchronous sensitivity lists on the named reset net to uniform synchronous `always @(posedge clk)` |
| `PINMISSING` | missing **output** port only: adds an explicit empty connection `/* verilator lint_off PINCONNECTEMPTY */ .<port>() /* verilator lint_on PINCONNECTEMPTY */` on the instance's last connection line. This silences the warning; it does not prove the output was meant to be unused, so review it. Missing **input** ports are never tied to zero (that would hide a real bug, such as a forgotten enable), so those instances are skipped, as are inouts, modules not declared in the same file, and positional or `.*` instances |

Each rule is one module (`blkseq.py`, `combdly.py`, `caseincomplete.py`, `latch.py`, `widthexpand.py`, `widthtrunc.py`, `undriven.py`, `unusedsignal.py`, `syncasyncnet.py`, `pinmissing.py`) with `RULES`,
`CLEARED_RULES` and a pure `fix_source(text, lines)`. The shared loop is in `core.py`.
Rules run in that order, and later rules see the earlier fixes.

## Running

```bash
# Run all rules against one design
python -m autofix.core examples/fifo

# Run against all designs in examples/
python -m autofix.core --all

# Run with a single rule
python -m autofix.core examples/fifo --rule BLKSEQ

# JSON summary output
python -m autofix.core examples/fifo --json results/fifo_autofix.json
```

## Golden Invariant

The autofix tool **must never introduce a semantic regression**. When run against
`examples/*/golden/`, it must report zero changes needed:

```bash
python -m autofix.core --all --golden-check
# exits 0 if and only if all golden designs are untouched
```
