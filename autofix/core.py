"""Shared autofix engine.

A rule is a module with:
    RULES          set of Verilator rule names it fixes
    CLEARED_RULES  set of rule names that must be gone after the fix
    fix_source(text, lines) -> (new_text, fixed_lines)   (lines are 1-based)

For each rule, in order, the engine lints the current text, fixes the flagged lines on a
copy, re-lints, and keeps the change only if CLEARED_RULES are gone and no new rule shows
up. Rules are applied one after another, so later rules see the earlier fixes. The original
file is never edited; the fixed design is written to the output directory.

Attempt rows follow docs/results_schema.md (autofix.attempts). `verified` is true only if
the lint check passed AND the design's testbench prints PASS, so it needs run_tb=True.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DIAG = re.compile(
    r"%(?:Warning|Error)-(?P<rule>[A-Z0-9_]+):\s*(?P<file>.+?):(?P<line>\d+)(?::\d+)?:"
)


def normalize_path(p):
    return str(p).replace("\\", "/")


def verilator_cmd():
    """Command prefix for verilator. On Windows 'verilator' is a perl script."""
    exe = shutil.which("verilator")
    if exe is None and os.name == "nt":
        # the extensionless perl script is invisible to which() on Windows
        for d in os.environ.get("PATH", "").split(os.pathsep):
            candidate = Path(d.strip('"')) / "verilator"
            if candidate.is_file():
                exe = str(candidate)
                break
    if exe is None:
        raise RuntimeError("verilator not found on PATH")
    if os.name == "nt" and not exe.lower().endswith((".exe", ".bat", ".cmd")):
        return ["perl", exe]
    return [exe]


def have_verilator():
    try:
        verilator_cmd()
        return True
    except RuntimeError:
        return False


def lint(path):
    """Return [(rule, line), ...] for every diagnostic Verilator prints for path."""
    res = subprocess.run(
        verilator_cmd() + ["--lint-only", "-Wall", str(path)], capture_output=True, text=True
    )
    out = res.stderr + "\n" + res.stdout
    return [(m.group("rule"), int(m.group("line"))) for m in DIAG.finditer(out)]


def lint_text(text, workdir, name):
    """Lint text by writing it to workdir/<name>.v (the file name must match the module)."""
    workdir.mkdir(parents=True, exist_ok=True)
    f = workdir / f"{name}.v"
    f.write_text(text, encoding="utf-8", newline="\n")
    return lint(f)


def run_testbench(design, tb, top, workdir, cwd=None, timeout=60):
    """Build and run the testbench. Returns 'PASS', 'FAIL', 'TIMEOUT' or 'NOT BUILDABLE'."""
    # absolute paths: the build runs with cwd set to the example folder
    design, tb, workdir = Path(design).resolve(), Path(tb).resolve(), Path(workdir).resolve()
    mdir = workdir / "obj_dir"
    cmd = verilator_cmd() + [
        "--binary", "--timing", "-Wno-fatal", "-CFLAGS", "-std=gnu++17",
        "--top-module", top, "--Mdir", str(mdir), str(design), str(tb),
    ]
    try:
        if subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).returncode != 0:
            return "NOT BUILDABLE"
        exe = mdir / f"V{top}"
        if not exe.exists():
            exe = exe.with_suffix(".exe")
        res = subprocess.run([str(exe)], cwd=cwd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return "TIMEOUT"
    finally:
        shutil.rmtree(mdir, ignore_errors=True)
    out = res.stdout + res.stderr
    ok = res.returncode == 0 and re.search(r"^PASS\b", out, re.M) and "FAIL" not in out
    return "PASS" if ok else "FAIL"


def _hunks(old, new, warn_lines):
    """Yield (line, before, after) for each changed region. `line` is the warning it belongs to."""
    a, b = old.split("\n"), new.split("\n")
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b).get_opcodes():
        if tag == "equal":
            continue
        owner = [w for w in warn_lines if w <= i1 + 1]
        line = max(owner) if owner else i1 + 1
        yield line, "\n".join(x.strip() for x in a[i1:i2]), "\n".join(x.strip() for x in b[j1:j2])


def _repo_path(path):
    p = Path(path)
    try:
        p = p.resolve().relative_to(Path.cwd().resolve())
    except ValueError:
        pass
    return normalize_path(p)


def fix_design(design_result, examples_dir, out_dir, rules, run_tb=False, require_pass=False):
    name = design_result["name"]
    src_path = Path(examples_dir) / name / "buggy" / f"{name}.v"
    text = src_path.read_text(encoding="utf-8")
    dest = Path(out_dir) / name
    work_cur, work_new = dest / "_cur", dest / "_new"
    file_field = _repo_path(src_path)

    before = {r for r, _ in lint(src_path)}
    cur_text, cur_rules = text, before
    attempts, fixed_lines = [], set()

    try:
        for rule in rules:
            findings = lint_text(cur_text, work_cur, name)
            cur_rules = {r for r, _ in findings}
            lines = [ln for r, ln in findings if r in rule.RULES]
            if not lines:
                continue
            new_text, fixed = rule.fix_source(cur_text, lines)
            if not fixed or new_text == cur_text:
                continue
            after = {r for r, _ in lint_text(new_text, work_new, name)}
            ok = not (after & rule.CLEARED_RULES) and not (after - cur_rules)
            rule_name = sorted(rule.RULES)[0]
            for line, b, a in _hunks(cur_text, new_text, lines):
                attempts.append({
                    "design": name, "rule": rule_name, "file": file_field, "line": line,
                    "before": b, "after": a, "verified": False, "_lint_ok": ok,
                })
            if ok:
                cur_text = new_text
                fixed_lines.update(fixed)
    finally:
        shutil.rmtree(work_cur, ignore_errors=True)
        shutil.rmtree(work_new, ignore_errors=True)

    result = {"design": name, "fixed_lines": sorted(fixed_lines), "attempts": attempts,
              "rules_before": sorted(before)}
    if not attempts:
        result["status"] = "nothing to fix"
        return result
    if cur_text == text:
        result.update(status="reverted", rules_after=sorted(before))
        _finish_rows(attempts, None)
        return result

    dest.mkdir(parents=True, exist_ok=True)
    out_file = dest / f"{name}.v"
    out_file.write_text(cur_text, encoding="utf-8", newline="\n")
    result["rules_after"] = sorted({r for r, _ in lint(out_file)})

    tb_status = None
    if run_tb or require_pass:
        tb = Path(examples_dir) / name / f"tb_{name}.v"
        tb_status = run_testbench(out_file, tb, f"tb_{name}", dest, cwd=Path(examples_dir) / name)
        result["testbench"] = tb_status
    _finish_rows(attempts, tb_status)

    if require_pass and tb_status != "PASS":
        out_file.unlink()
        result["status"] = "reverted"
    else:
        result["status"] = "kept"
    return result


def _finish_rows(attempts, tb_status):
    """Set `verified` and `note`, and drop internal keys."""
    for row in attempts:
        lint_ok = row.pop("_lint_ok")
        if not lint_ok:
            row["note"] = "Lint did not clear this warning, or the fix added a new warning; reverted."
        elif tb_status is None:
            row["note"] = "Lint clean for this warning. Regression was not run."
        elif tb_status == "PASS":
            row["verified"] = True
            row["note"] = "Lint clean for this warning, regression still passes."
        else:
            row["note"] = (f"Lint clean for this warning, but the testbench result is {tb_status} "
                           "(other planted bugs remain unfixed).")


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_section(out_path, attempts):
    """Replace only the `autofix` section of results.json, keeping everything else."""
    out_path = Path(out_path)
    doc = json.loads(out_path.read_text(encoding="utf-8")) if out_path.exists() else {}
    now = _now()
    doc.setdefault("schema_version", 1)
    doc.setdefault("run", {"id": now.replace(":", "-") + "-local", "started_at": now,
                           "verilator_version": _verilator_version()})
    doc["autofix"] = {"generated_at": now, "attempts": attempts}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(out_path)
    return doc


def _verilator_version():
    out = subprocess.run(verilator_cmd() + ["--version"], capture_output=True, text=True).stdout
    m = re.search(r"Verilator\s+([\d.]+)", out)
    return m.group(1) if m else "unknown"


def all_rules():
    from autofix import blkseq, caseincomplete, combdly
    return [blkseq, combdly, caseincomplete]


def main(argv=None, rules=None):
    ap = argparse.ArgumentParser(description="Apply safe lint autofixes to the buggy examples")
    ap.add_argument("--lint", default="results/lint.json",
                    help="lint.json listing the designs; if missing, every examples/*/buggy design is used")
    ap.add_argument("--examples", default="examples")
    ap.add_argument("--out", default="results/autofix")
    ap.add_argument("--results", help="also write the autofix section of this results.json")
    ap.add_argument("--regress", action="store_true",
                    help="run the testbench on the fixed design and set `verified` from it")
    ap.add_argument("--require-pass", action="store_true",
                    help="revert the fixed file unless the testbench prints PASS (implies --regress)")
    args = ap.parse_args(argv)
    rules = rules or all_rules()

    lint_json = Path(args.lint)
    if lint_json.exists():
        names = [d["name"] for d in json.loads(lint_json.read_text(encoding="utf-8"))["designs"]]
    else:
        names = sorted(p.name for p in Path(args.examples).iterdir()
                       if (p / "buggy" / f"{p.name}.v").exists())

    results = [fix_design({"name": n}, args.examples, args.out, rules, args.regress, args.require_pass)
               for n in names]
    for r in results:
        tb = f", testbench {r['testbench']}" if "testbench" in r else ""
        print(f"{r['design']}: {r['status']}, fixed lines {r['fixed_lines']}{tb}")
    if args.results:
        write_section(args.results, [a for r in results for a in r["attempts"]])
        print(f"wrote autofix section to {args.results}")
    return 0 if all(r["status"] in ("kept", "nothing to fix") for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
