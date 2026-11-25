# Coverage Advisor

`coverage_advisor` is the verification coverage analysis tool for VeriPilot.

## Features
- Compiles designs and testbenches using Verilator `--coverage` (`--timing` enabled).
- Runs the compiled simulation binary to generate `coverage.dat`.
- Annotates line and toggle coverage using `verilator_coverage`.
- Parses the annotated coverage reports to identify covered percentages and specific uncovered lines/branches.
- Produces structured JSON reports for regression and dashboard consumption.
- Integrates unified `coverage` and `stimulus` sections into `results/results.json`.

## Usage
Run coverage analysis across the supported designs (`fifo`, `spi`, `timer`):

```bash
python coverage_advisor/advisor.py
```

Run for a specific design:
```bash
python coverage_advisor/advisor.py fifo
```

Outputs are generated in `coverage_advisor/reports/<design>_coverage.json`:
```json
{
  "name": "fifo",
  "covered_percent": 100.0,
  "uncovered": []
}
```

## Testing
Run unit tests with Python unittest or pytest:
```bash
python -m unittest coverage_advisor/test_advisor.py
python -m unittest coverage_advisor/test_stimulus_advisor.py
```

## Rule-Based Stimulus Synthesis Scaffolding (`stimulus_advisor.py`)

`coverage_advisor/stimulus_advisor.py` analyzes the uncovered branches and lines reported by `advisor.py` and synthesizes targeted stimulus to reach those cases.

### Key Architecture & Principles
- **Scaffolding & Extension Interface**: Implements deterministic rule-based heuristics for common RTL corner cases (state machine default branches, counter boundaries, FIFO depth limits). Serves as the plug-in interface where an LLM agent will connect in future work.
- **Dynamic Context Parsing**: Uncovered lines are analyzed dynamically via `extract_uncovered_context()` rather than matching hardcoded line numbers.
- **Non-Destructive Sandbox**: All patched testbenches and simulations execute inside an isolated `tempfile.TemporaryDirectory()`. Committed files under `examples/` are **never** modified.
- **Coverage Improvement Evaluation & Ceilings**:
  - `fifo`: 100.0% -> 100.0% (`already_clean`).
  - `spi`: 83.33% -> 83.33% (`no_coverage_increase`). The remaining uncovered branch is defensive `default: state <= IDLE;` in a 2-bit FSM where only 3 valid states (00, 01, 10) exist. State 11 is unreachable by design in normal simulation, representing an 83.33% ceiling.
  - `timer`: 95.83% -> 95.83% (`no_coverage_increase`). The remaining uncovered branch is defensive `default: next_state = IDLE;` in a 2-bit FSM, representing a 95.83% ceiling.
- **Pipeline Integration**: Can be run without `PYTHONPATH=.`. Records results in `coverage_advisor/reports/stimulus_report.json` and updates `results/results.json`.

Run stimulus synthesis across designs:
```bash
python coverage_advisor/stimulus_advisor.py fifo spi timer
```
