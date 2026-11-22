"""Shared autofix engine.

A rule is a module with:
    RULES          set of Verilator rule names it fixes
    CLEARED_RULES  set of rule names that must be gone after the fix
    PARTIAL        optional, True if some warnings of the rule can't be fixed; then the fix
                   must remove one warning per fixed line instead of the whole rule name
    fix_source(text, lines) -> (new_text, fixed_lines)   (lines are 1-based)

For each rule, in order, the engine lints the current text, fixes the flagged lines on a
copy, re-lints, and keeps the change only if CLEARED_RULES are gone and no new rule shows
up. Rules are applied one after another, so later rules see the earlier fixes. The original
file is never edited; the fixed design is written to the output directory.

Attempt rows follow docs/results_schema.md (autofix.attempts). By default the testbench is
run before and after every fix. A fix is `verified` only when its warning is gone, no new
warning appears, the design builds, and the testbench ends in PASS. A fix that is lint clean and
no worse than before (NOT BUILDABLE < FAIL/TIMEOUT < PASS) but does not reach PASS is still
kept, so later fixes can build on it, but it is not verified. The two testbench results are
recorded on the row as the extra fields `regression_before` and `regression_after`. A fix that
makes things worse is reverted.
"""

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from regress import runner as _regress

DIAG = re.compile(
    r"%(?:Warning|Error)-(?P<rule>[A-Z0-9_]+):\s*(?P<file>.+?):(?P<line>\d+)(?::\d+)?:"
)


def normalize_path(p):
    return str(p).replace("\\", "/")


def verilator_cmd():
    """Command prefix for verilator. Shared with the regress runner (handles the Windows perl script)."""
    return _regress._tool_cmd("verilator")


def have_verilator():
    try:
        _regress.verilator_version()
        return True
    except (OSError, RuntimeError, subprocess.CalledProcessError):
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


# Testbench results from worst to best. A fix may not move the result down this scale.
TB_RANK = {"NOT BUILDABLE": 0, "TIMEOUT": 1, "FAIL": 1, "PASS": 2}


def _tb_of(text, name, examples_dir, workdir):
    """Write text as <name>.v in workdir and return the testbench result for it."""
    workdir = Path(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    f = workdir / f"{name}.v"
    f.write_text(text, encoding="utf-8", newline="\n")
    ex = Path(examples_dir) / name
    return run_testbench(f, ex / f"tb_{name}.v", f"tb_{name}", workdir, cwd=ex)


def _judge(lint_ok, regress, tb_before, tb_after):
    """Return (verified, keep, note) for one fix. tb_after is None when no testbench was run.

    verified: warning gone, nothing new, and the testbench ends in PASS.
    keep:     lint clean and the testbench is no worse than before (or regression was skipped).
    """
    if not lint_ok:
        return False, False, "Lint did not clear this warning, or the fix added a new warning; reverted."
    if not regress:
        return False, True, "Lint clean for this warning. Regression was not run, so not verified."
    if tb_after == "NOT BUILDABLE":
        return False, False, f"Lint clean, but the design does not build after the fix (before: {tb_before}); reverted."
    if TB_RANK[tb_after] < TB_RANK[tb_before]:
        return False, False, f"Lint clean, but the testbench got worse ({tb_before} -> {tb_after}); reverted."
    if tb_after == "PASS":
        return True, True, f"Lint clean for this warning, design builds, testbench {tb_before} -> PASS."
    return False, True, (f"Lint clean for this warning and the design builds, but the testbench is {tb_after} "
                         f"(before: {tb_before}), so not verified. Kept as progress.")


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


def fix_design(design_result, examples_dir, out_dir, rules, regress=True, require_pass=False):
    """Apply rules to one design. `regress` runs the testbench before and after every fix.

    A fix is kept when it is lint clean and the testbench is no worse (see _judge), and marked
    verified only when the testbench ends in PASS. Without `regress` it is kept on a clean
    lint, never verified. `require_pass` implies `regress` and also deletes the
    fixed file unless the final testbench prints PASS.
    """
    regress = regress or require_pass
    name = design_result["name"]
    src_path = Path(examples_dir) / name / "buggy" / f"{name}.v"
    text = src_path.read_text(encoding="utf-8")
    dest = Path(out_dir) / name
    work_cur, work_new, work_tb = dest / "_cur", dest / "_new", dest / "_tb"
    file_field = _repo_path(src_path)

    before = {r for r, _ in lint(src_path)}
    cur_text = text
    attempts, fixed_lines = [], set()
    tb_cur = None

    try:
        if regress:
            tb_cur = _tb_of(text, name, examples_dir, work_tb)
        for rule in rules:
            findings = lint_text(cur_text, work_cur, name)
            cur_rules = {r for r, _ in findings}
            lines = [ln for r, ln in findings if r in rule.RULES]
            if not lines:
                continue
            new_text, fixed = rule.fix_source(cur_text, lines)
            if not fixed or new_text == cur_text:
                continue
            after_findings = lint_text(new_text, work_new, name)
            after = {r for r, _ in after_findings}
            if getattr(rule, "PARTIAL", False):
                # The rule cannot fix every warning of its kind (e.g. ports), so the rule name
                # may stay. Require that each fixed line removed one of its warnings instead.
                n_before = sum(1 for r, _ in findings if r in rule.CLEARED_RULES)
                n_after = sum(1 for r, _ in after_findings if r in rule.CLEARED_RULES)
                lint_ok = n_after <= n_before - len(fixed) and not (after - cur_rules)
            else:
                lint_ok = not (after & rule.CLEARED_RULES) and not (after - cur_rules)
            tb_new = _tb_of(new_text, name, examples_dir, work_tb) if (regress and lint_ok) else None
            verified, keep, note = _judge(lint_ok, regress, tb_cur, tb_new)
            rule_name = sorted(rule.RULES)[0]
            for line, b, a in _hunks(cur_text, new_text, lines):
                row = {"design": name, "rule": rule_name, "file": file_field, "line": line,
                       "before": b, "after": a, "verified": verified, "note": note}
                if regress:
                    row["regression_before"] = tb_cur
                    if tb_new is not None:
                        row["regression_after"] = tb_new
                attempts.append(row)
            if keep:
                cur_text = new_text
                fixed_lines.update(fixed)
                if regress:
                    tb_cur = tb_new
    finally:
        for w in (work_cur, work_new, work_tb):
            shutil.rmtree(w, ignore_errors=True)

    result = {"design": name, "fixed_lines": sorted(fixed_lines), "attempts": attempts,
              "rules_before": sorted(before)}
    if regress:
        result["testbench"] = tb_cur
    if not attempts:
        result["status"] = "nothing to fix"
        return result
    if cur_text == text:
        result.update(status="reverted", rules_after=sorted(before))
        return result

    dest.mkdir(parents=True, exist_ok=True)
    out_file = dest / f"{name}.v"
    out_file.write_text(cur_text, encoding="utf-8", newline="\n")
    result["rules_after"] = sorted({r for r, _ in lint(out_file)})

    if require_pass and tb_cur != "PASS":
        out_file.unlink()
        result["status"] = "reverted"
    else:
        result["status"] = "kept"
    return result


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
    from autofix import blkseq, caseincomplete, combdly, latch, widthexpand, widthtrunc, undriven, unusedsignal, syncasyncnet
    return [blkseq, combdly, caseincomplete, latch, widthexpand, widthtrunc, undriven, unusedsignal, syncasyncnet]


def main(argv=None, rules=None):
    ap = argparse.ArgumentParser(description="Apply safe lint autofixes to the buggy examples")
    ap.add_argument("--lint", default="results/lint.json",
                    help="lint.json listing the designs; if missing, every examples/*/buggy design is used")
    ap.add_argument("--examples", default="examples")
    ap.add_argument("--out", default="results/autofix")
    ap.add_argument("--results", help="also write the autofix section of this results.json")
    ap.add_argument("--no-regress", action="store_true",
                    help="skip the testbench: fixes are kept on a clean re-lint but never `verified`")
    ap.add_argument("--require-pass", action="store_true",
                    help="strict mode: delete the fixed file unless the final testbench prints PASS")
    args = ap.parse_args(argv)
    rules = rules or all_rules()

    lint_json = Path(args.lint)
    if lint_json.exists():
        names = [d["name"] for d in json.loads(lint_json.read_text(encoding="utf-8"))["designs"]]
    else:
        names = sorted(p.name for p in Path(args.examples).iterdir()
                       if (p / "buggy" / f"{p.name}.v").exists())

    results = [fix_design({"name": n}, args.examples, args.out, rules, not args.no_regress, args.require_pass)
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
