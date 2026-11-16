"""Regression runner: build one example testbench with Verilator, run it for
one or more seeds, and write the `regression` section of results/results.json.

    python -m regress.runner                      # fifo, seed 1
    python -m regress.runner spi --seeds 1 2 3

The testbenches fix their own `$random` seed, so the seed given here is passed
to Verilator (`+verilator+seed`, with random initial values enabled). It varies
the power-up state of the design, not the testbench stimulus.
See docs/results_schema.md.
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
    """Resolve a Verilator tool. On native Windows the scripts are Perl files."""
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
    out = subprocess.run(_tool_cmd("verilator") + ["--version"],
                         capture_output=True, text=True, check=True).stdout
    m = re.search(r"Verilator\s+([\d.]+)", out)
    if not m:
        raise RuntimeError(f"cannot parse Verilator version from: {out!r}")
    return m.group(1)


def build(design: str, root: Path, mdir: Path) -> Path:
    """Compile the golden RTL with its testbench. Returns the simulator path."""
    ex = root / "examples" / design
    rtl, tb = ex / "golden" / f"{design}.v", ex / f"tb_{design}.v"
    for f in (rtl, tb):
        if not f.exists():
            raise FileNotFoundError(f)
    top = f"tb_{design}"
    cmd = _tool_cmd("verilator") + [
        "--binary", "--timing", "-Wno-fatal", "-CFLAGS", "-std=gnu++17",
        "--top-module", top, "--Mdir", str(mdir), str(rtl), str(tb),
    ]
    res = subprocess.run(cmd, cwd=ex, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Verilator build failed for {design}:\n{res.stderr or res.stdout}")
    exe = mdir / (f"V{top}.exe" if os.name == "nt" else f"V{top}")
    return exe


def classify(returncode: int, output: str) -> str:
    """'pass' only on a clean exit, a PASS line and no line starting with FAIL."""
    if (returncode == 0 and re.search(r"^PASS\b", output, re.M)
            and not re.search(r"^\s*FAIL\b", output, re.M)):
        return "pass"
    return "fail"


def run_seed(design: str, exe: Path, seed: int, cwd: Path, timeout: float = 300) -> dict:
    start = time.perf_counter()
    try:
        res = subprocess.run(
            [str(exe), f"+verilator+seed+{seed}", "+verilator+rand+reset+2"],
            cwd=cwd, capture_output=True, text=True, timeout=timeout)
        status = classify(res.returncode, res.stdout + res.stderr)
    except subprocess.TimeoutExpired:
        status = "fail"
    return {
        "design": design,
        "test": f"tb_{design}",
        "status": status,
        "seed": seed,
        "duration_s": round(time.perf_counter() - start, 3),
    }


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_section(out_path: Path, tests: list[dict], version: str) -> dict:
    """Update only the `regression` section, keeping everything else.

    Rows are merged by (design, test, seed): a new row replaces an old row with
    the same key, other rows stay. So running fifo, then spi, keeps both.
    """
    doc = {}
    if out_path.exists():
        doc = json.loads(out_path.read_text(encoding="utf-8"))
    now = _now()
    doc.setdefault("schema_version", 1)
    doc.setdefault("run", {"id": now.replace(":", "-") + "-local",
                           "started_at": now, "verilator_version": version})
    old = doc.get("regression", {}).get("tests", [])
    merged = {(t["design"], t["test"], t["seed"]): t for t in old}
    merged.update({(t["design"], t["test"], t["seed"]): t for t in tests})
    doc["regression"] = {"generated_at": now, "tests": list(merged.values())}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return doc


def run(design: str, seeds: list[int], out_path: Path, root: Path = REPO_ROOT) -> list[dict]:
    version = verilator_version()
    if version != REQUIRED_VERILATOR:
        raise RuntimeError(f"Verilator {REQUIRED_VERILATOR} required, found {version}")
    with tempfile.TemporaryDirectory(prefix="veripilot_regress_") as tmp:
        exe = build(design, root, Path(tmp) / "obj_dir")
        tests = [run_seed(design, exe, s, root / "examples" / design) for s in seeds]
    write_section(out_path, tests, version)
    return tests


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("design", nargs="?", default="fifo")
    p.add_argument("--seeds", type=int, nargs="+", default=[1])
    p.add_argument("--out", type=Path, default=REPO_ROOT / "results" / "results.json")
    args = p.parse_args(argv)
    try:
        tests = run(args.design, args.seeds, args.out)
    except (RuntimeError, FileNotFoundError, OSError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    for t in tests:
        print(f"{t['test']} seed={t['seed']} {t['status']} {t['duration_s']}s")
    print(f"wrote {args.out}")
    return 0 if all(t["status"] == "pass" for t in tests) else 1


if __name__ == "__main__":
    sys.exit(main())
