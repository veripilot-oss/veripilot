# Coverage Advisor

`coverage_advisor` is the verification coverage analysis tool for VeriPilot.

## Features
- Compiles designs and testbenches using Verilator `--coverage` (`--timing` enabled).
- Runs the compiled simulation binary to generate `coverage.dat`.
- Annotates line and toggle coverage using `verilator_coverage`.
- Parses the annotated coverage reports to identify covered percentages and specific uncovered lines/branches.
- Produces structured JSON reports for regression and dashboard consumption.

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
  "covered_percent": 87.5,
  "uncovered": [
    {
      "file": "examples/fifo/golden/fifo.v",
      "line": 42,
      "kind": "line_or_branch",
      "code": "full <= 1'b1;"
    }
  ]
}
```

## Testing
Run unit tests with Python unittest or pytest:
```bash
python -m unittest coverage_advisor/test_advisor.py
python -m unittest coverage_advisor/test_stimulus_advisor.py
```

## Rule-Based Stimulus Synthesis (`stimulus_advisor.py`)

`coverage_advisor/stimulus_advisor.py` analyzes the uncovered branches/lines reported by `advisor.py` and synthesizes targeted stimulus to reach those cases.

Key design principles:
- **Rule-Based Synthesis**: Currently implements deterministic patterns for common RTL edge conditions (e.g. state default branches, boundary limits).
- **LLM Extension Point**: `generate_targeted_stimulus()` serves as the explicit integration interface where an external LLM will plug in to synthesize novel test stimulus.
- **Non-Destructive Sandbox**: All patched testbenches and simulations run inside an isolated temporary directory. Files under `examples/` are **never** modified.
- **Coverage Improvement Gate**: Stimulus improvements are tracked and recorded with `baseline_percent`, `final_percent`, and `status`.

Run stimulus synthesis across designs:
```bash
python coverage_advisor/stimulus_advisor.py fifo spi timer
```

