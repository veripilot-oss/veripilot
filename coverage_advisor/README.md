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
```
