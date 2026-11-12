"""Autofix for BLKSEQ: blocking assignment '=' inside a clocked always block.

Reads results/lint.json, changes the first plain '=' on each flagged line to '<=',
and keeps the result only if re-linting shows the BLKSEQ / BLKANDNBLK findings are
gone and no new rule shows up. BLKANDNBLK is reported on the register declaration
and disappears once every blocking assignment to that register is fixed, so it is
not edited separately.

The fixed file is written to an output directory. The original is never edited.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

RULES = {"BLKSEQ"}
CLEARED_RULES = {"BLKSEQ", "BLKANDNBLK"}
# first '=' that is not part of ==, !=, <=, >=, =>
ASSIGN = re.compile(r"(?<![=!<>])=(?![=>])")
DIAG = re.compile(r"%(?:Warning|Error)-(?P<rule>[A-Z0-9_]+):")


def normalize_path(p):
    return str(p).replace("\\", "/")


def fix_source(text, lines_to_fix):
    """Return (new_text, fixed_lines). lines_to_fix are 1-based line numbers."""
    src = text.split("\n")
    fixed = []
    for n in sorted(set(lines_to_fix)):
        if not 1 <= n <= len(src):
            continue
        line = src[n - 1]
        code, sep, comment = line.partition("//")
        new_code, count = ASSIGN.subn("<=", code, count=1)
        if count:
            src[n - 1] = new_code + sep + comment
            fixed.append(n)
    return "\n".join(src), fixed


def verilator_cmd():
    """Command prefix for verilator. On Windows 'verilator' is a perl script."""
    exe = shutil.which("verilator")
    if exe is None and os.name == "nt":
        # the extensionless perl script is invisible to which() on Windows
        for d in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(d) / "verilator"
            if candidate.is_file():
                exe = str(candidate)
                break
    if exe is None:
        raise RuntimeError("verilator not found on PATH")
    if os.name == "nt" and not exe.lower().endswith((".exe", ".bat", ".cmd")):
        return ["perl", exe]
    return [exe]


def lint_rules(path):
    res = subprocess.run(
        verilator_cmd() + ["--lint-only", "-Wall", str(path)], capture_output=True, text=True
    )
    return {m.group("rule") for m in DIAG.finditer(res.stderr + "\n" + res.stdout)}


def run_testbench(design, tb, top, workdir):
    """Build and run the testbench. Returns 'PASS', 'FAIL' or 'NOT BUILDABLE'."""
    cmd = verilator_cmd() + [
        "--binary", "--timing", "-Wall", "-Wno-fatal", "-CFLAGS", "-std=gnu++17",
        "--top-module", top, "--Mdir", str(Path(workdir) / "obj_dir"), str(design), str(tb),
    ]
    if subprocess.run(cmd, capture_output=True, text=True).returncode != 0:
        return "NOT BUILDABLE"
    exe = Path(workdir) / "obj_dir" / f"V{top}"
    if not exe.exists():
        exe = exe.with_suffix(".exe")
    out = subprocess.run([str(exe)], capture_output=True, text=True, timeout=300)
    return "PASS" if re.search(r"^PASS", out.stdout, re.M) else "FAIL"


def fix_design(design_result, examples_dir, out_dir, require_pass=False):
    name = design_result["name"]
    findings = [f for f in design_result["findings"] if f["rule"] in RULES]
    if not findings:
        return {"design": name, "status": "nothing to fix", "fixed_lines": []}

    src_path = Path(examples_dir) / name / "buggy" / f"{name}.v"
    text = src_path.read_text(encoding="utf-8")
    new_text, fixed = fix_source(text, [f["line"] for f in findings])
    if not fixed:
        return {"design": name, "status": "no change", "fixed_lines": []}

    dest = Path(out_dir) / name
    dest.mkdir(parents=True, exist_ok=True)
    out_file = dest / f"{name}.v"
    out_file.write_text(new_text, encoding="utf-8", newline="\n")

    before = lint_rules(src_path)
    after = lint_rules(out_file)
    ok = not (after & CLEARED_RULES) and not (after - before)
    result = {"design": name, "fixed_lines": fixed, "rules_before": sorted(before), "rules_after": sorted(after)}

    if ok and require_pass:
        tb = Path(examples_dir) / name / f"tb_{name}.v"
        result["testbench"] = run_testbench(out_file, tb, f"tb_{name}", dest)
        ok = result["testbench"] == "PASS"

    if ok:
        result["status"] = "kept"
    else:
        out_file.unlink()
        result["status"] = "reverted"
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description="Fix BLKSEQ findings from results/lint.json")
    ap.add_argument("--lint", default="results/lint.json")
    ap.add_argument("--examples", default="examples")
    ap.add_argument("--out", default="results/autofix")
    ap.add_argument("--require-pass", action="store_true",
                    help="also require the testbench to print PASS (only possible once every planted bug is fixed)")
    args = ap.parse_args(argv)

    data = json.loads(Path(args.lint).read_text(encoding="utf-8"))
    results = [fix_design(d, args.examples, args.out, args.require_pass) for d in data["designs"]]
    for r in results:
        print(f"{r['design']}: {r['status']}, lines {r['fixed_lines']}")
    return 0 if all(r["status"] in ("kept", "nothing to fix") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
