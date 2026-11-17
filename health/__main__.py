"""Write the `health` section of results/results.json.

    python -m health [--results results/results.json]

Reads the file, computes the score with health.score.compute_health, and replaces only the
`health` section. Every other section is left untouched. If nothing can be measured the
section is not written (see docs/results_schema.md).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from health.score import compute_health


def write_health_section(path: Path) -> dict | None:
    """Add or replace the health section in `path`. Returns the section, or None if nothing was measurable."""
    if not path.exists():
        raise FileNotFoundError(f"{path} not found. Run the pipeline stages first.")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as err:
        raise RuntimeError(f"Cannot update corrupt {path}: {err}") from err

    result = compute_health(doc)
    if result is None:
        doc.pop("health", None)
        section = None
    else:
        section = {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **result}
        doc["health"] = section

    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return section


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Compute the health score and write it into results.json")
    ap.add_argument("--results", type=Path, default=Path("results/results.json"))
    args = ap.parse_args(argv)
    try:
        section = write_health_section(args.results)
    except (FileNotFoundError, RuntimeError) as err:
        print(f"error: {err}", file=sys.stderr)
        return 1
    if section is None:
        print("nothing measurable yet; no health section written")
    else:
        print(f"health score {section['score']} {section['components']}")
        print(f"updated health section in {args.results}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
