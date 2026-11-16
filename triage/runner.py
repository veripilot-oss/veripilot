"""Triage tool: rerun failing tests across several seeds and classify them as
repeatable (fails on all seeds) or flaky (passes on some seeds, fails on others).

Writes results into the `triage` section of results/results.json.

Usage:
    python -m triage.runner fifo --seeds 1 2 3 4 5
    python -m triage.runner fifo --test tb_fifo_flaky --seeds 1 2 3 4 5
    python -m triage.runner fifo --variant buggy --seeds 1 2 3 4 5
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_VERILATOR = "5.034"
REPO_ROOT = Path(__file__).resolve().parent.parent


def _tool_cmd(name: str) -> list[str]:
    """Resolve a tool across Linux and Windows MSYS2/native environments."""
    found = shutil.which(name)
    if found and found.endswith((".exe", ".bat", ".cmd")):
        return [found]
    for d in os.environ.get("PATH", "").split(os.pathsep):
        candidate = os.path.join(d.strip('"'), name)
        if os.path.isfile(candidate):
            if os.name == "nt":
                return [shutil.which("perl") or "perl", candidate]
            return [candidate]
    return [shutil.which("perl") or "perl", name] if os.name == "nt" else [name]


def verilator_version() -> str:
    out = subprocess.run(
        _tool_cmd("verilator") + ["--version"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    m = re.search(r"Verilator\s+([\d.]+)", out)
    if not m:
        raise RuntimeError(f"cannot parse Verilator version from: {out!r}")
    return m.group(1)


def build_test(
    design: str,
    test_name: str,
    variant: str,
    root: Path,
    mdir: Path,
) -> Path:
    """Build the target RTL and testbench with Verilator."""
    ex = root / "examples" / design
    rtl = ex / variant / f"{design}.v"
    tb = ex / f"{test_name}.v"

    # Allow standalone testbench if rtl does not exist
    sources = []
    if rtl.exists():
        sources.append(str(rtl))
    if tb.exists():
        sources.append(str(tb))
    else:
        raise FileNotFoundError(f"Testbench not found: {tb}")

    top = test_name
    cmd = _tool_cmd("verilator") + [
        "--binary",
        "--timing",
        "-Wno-fatal",
        "-CFLAGS",
        "-std=gnu++17",
        "--top-module",
        top,
        "--Mdir",
        str(mdir),
    ] + sources

    res = subprocess.run(cmd, cwd=ex, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(
            f"Verilator build failed for {design} ({test_name}, variant={variant}):\n"
            f"{res.stderr or res.stdout}"
        )
    exe = mdir / (f"V{top}.exe" if os.name == "nt" else f"V{top}")
    return exe


def classify_output(returncode: int, output: str) -> str:
    """'pass' only on a clean exit 0, a PASS keyword and no FAIL keyword."""
    if returncode == 0 and re.search(r"^PASS\b", output, re.M) and "FAIL" not in output:
        return "pass"
    return "fail"


def run_single_seed(
    exe: Path,
    seed: int,
    cwd: Path,
    timeout: float = 300,
) -> str:
    """Execute simulator executable with random seed parameters."""
    try:
        res = subprocess.run(
            [str(exe), f"+verilator+seed+{seed}", "+verilator+rand+reset+2"],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return classify_output(res.returncode, res.stdout + res.stderr)
    except subprocess.TimeoutExpired:
        return "fail"


def classify_triage(runs: int, failures: int) -> str:
    """Assign label based on rerun failure count:
    - all failed -> 'repeatable'
    - mixed passes and failures -> 'flaky'
    - no failures -> 'pass'
    """
    if failures == 0:
        return "pass"
    if failures == runs:
        return "repeatable"
    return "flaky"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_triage_section(out_path: Path, new_labels: list[dict], version: str) -> dict:
    """Update only the `triage` section of results/results.json preserving other keys."""
    doc = {}
    if out_path.exists():
        try:
            doc = json.loads(out_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            doc = {}
    now = _now()
    doc.setdefault("schema_version", 1)
    doc.setdefault(
        "run",
        {
            "id": now.replace(":", "-") + "-local",
            "started_at": now,
            "verilator_version": version,
        },
    )

    existing_labels = doc.get("triage", {}).get("labels", [])
    merged_map = {}
    for item in existing_labels:
        merged_map[(item.get("design"), item.get("test"))] = item
    for item in new_labels:
        merged_map[(item.get("design"), item.get("test"))] = item

    doc["triage"] = {
        "generated_at": now,
        "labels": list(merged_map.values()),
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return doc


def triage_test(
    design: str,
    test_name: str | None = None,
    variant: str = "golden",
    seeds: list[int] | None = None,
    out_path: Path | None = None,
    root: Path = REPO_ROOT,
) -> dict:
    """Rerun test across seeds, determine flaky vs repeatable, and record to results.json."""
    if seeds is None:
        seeds = [1, 2, 3, 4, 5]
    if test_name is None:
        test_name = f"tb_{design}"

    version = verilator_version()
    if version != REQUIRED_VERILATOR:
        raise RuntimeError(f"Verilator {REQUIRED_VERILATOR} required, found {version}")

    with tempfile.TemporaryDirectory(prefix="veripilot_triage_") as tmp:
        mdir = Path(tmp) / "obj_dir"
        exe = build_test(design, test_name, variant, root, mdir)
        ex_dir = root / "examples" / design

        results = [run_single_seed(exe, s, ex_dir) for s in seeds]

    runs = len(results)
    failures = sum(1 for r in results if r == "fail")
    label = classify_triage(runs, failures)

    triage_entry = {
        "design": design,
        "test": test_name,
        "label": label,
        "runs": runs,
        "failures": failures,
    }

    if out_path:
        write_triage_section(out_path, [triage_entry], version)

    return triage_entry


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("design", nargs="?", default="fifo", help="Target design name (e.g. fifo, spi, timer)")
    p.add_argument("--test", default=None, help="Specific testbench module/file name")
    p.add_argument("--variant", default="golden", choices=["golden", "buggy"], help="RTL variant to test")
    p.add_argument("--seeds", type=int, nargs="+", default=[1, 2, 3, 4, 5], help="Random seeds to evaluate")
    p.add_argument("--out", type=Path, default=REPO_ROOT / "results" / "results.json", help="Path to results.json")

    args = p.parse_args(argv)
    try:
        res = triage_test(
            design=args.design,
            test_name=args.test,
            variant=args.variant,
            seeds=args.seeds,
            out_path=args.out,
        )
    except (RuntimeError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    print(
        f"[{res['design']}:{res['test']}] label={res['label']} "
        f"({res['failures']}/{res['runs']} failures across seeds {args.seeds})"
    )
    print(f"updated triage section in {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
