"""VeriPilot Linter Tool: runs Verilator on benchmark designs, parses diagnostics,
compares with bugs.yaml ground truth, and writes results/lint.json.
"""

import os
import re
import sys
import json
import yaml
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _get_verilator_base_cmd():
    """Resolve Verilator base command across Linux and native Windows (MSYS2/UCRT64).
    On Windows native Python, shutil.which('verilator') returns None because the script
    has no .exe extension. Scans PATH for a file named 'verilator' and invokes it via
    Perl on Windows.
    """
    # 1. Standard which lookup (works on Linux or Windows when .exe/.bat exists)
    v = shutil.which("verilator")
    if v and (v.endswith(".exe") or v.endswith(".bat") or v.endswith(".cmd")):
        return [v]

    # 2. Scan each directory in PATH for an extensionless file named "verilator"
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for d in path_dirs:
        d = d.strip('"')
        candidate = os.path.join(d, "verilator")
        if os.path.isfile(candidate):
            if sys.platform.startswith("win") or os.name == "nt":
                perl = shutil.which("perl") or "perl"
                return [perl, candidate]
            return [candidate]

    # 3. Fallbacks
    if sys.platform.startswith("win") or os.name == "nt":
        perl = shutil.which("perl") or "perl"
        return [perl, "verilator"]
    return ["verilator"]


def get_verilator_version():
    cmd = _get_verilator_base_cmd() + ["--version"]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    m = re.search(r"Verilator\s+([\d.]+)", res.stdout)
    return m.group(1) if m else "5.034"


def parse_verilator_output(output_text, default_file=""):
    r"""Parse Verilator warnings and errors into structured finding dicts.
    Handles lines like:
      %Warning-PINMISSING: examples/fifo/buggy/fifo.v:90:25: Cell has missing pin...
      %Error-BLKANDNBLK: C:\repo\examples\fifo\buggy\fifo.v:59:9: Unsupported...
    """
    findings = []
    # Match %Warning-RULE or %Error-RULE: optional_drive:path:line:col: message
    pattern = re.compile(
        r"%(?P<severity>Warning|Error)-(?P<rule>[A-Z0-9_]+):\s*(?P<file>(?:[a-zA-Z]:)?[^:\n]+):(?P<line>\d+)(?::\d+)?:?\s*(?P<msg>[^\n]+)"
    )

    for line in output_text.splitlines():
        m = pattern.search(line)
        if m:
            sev = "error" if m.group("severity") == "Error" else "warning"
            rule = m.group("rule")
            raw_filepath = m.group("file").strip()
            # Normalize backslashes for cross-platform Windows/Linux compatibility
            normalized_filepath = raw_filepath.replace("\\", "/")
            if "buggy/" in normalized_filepath:
                rel_file = "buggy/" + normalized_filepath.split("buggy/")[-1]
            else:
                rel_file = normalized_filepath.split("/")[-1]

            lineno = int(m.group("line"))
            msg = m.group("msg").strip()

            findings.append({
                "rule": rule,
                "file": rel_file,
                "line": lineno,
                "severity": sev,
                "message": msg
            })
    return findings


def load_ground_truth(design_dir):
    bugs_yaml_path = Path(design_dir) / "bugs.yaml"
    if not bugs_yaml_path.exists():
        return []
    with open(bugs_yaml_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("bugs", []) if isinstance(data, dict) else []


def match_findings_to_bugs(findings, planted_bugs):
    """A bug is detected when a finding has the same rule AND the same line."""
    matched_bug_ids = set()
    result_findings = []

    for f in findings:
        matched_id = None
        for b in planted_bugs:
            if f["rule"] == b.get("rule") and f["line"] == b.get("line"):
                matched_id = b.get("id")
                matched_bug_ids.add(matched_id)
                break

        f_copy = dict(f)
        f_copy["matched_bug_id"] = matched_id
        result_findings.append(f_copy)

    all_bug_ids = {b["id"] for b in planted_bugs if "id" in b}
    missed_ids = sorted(list(all_bug_ids - matched_bug_ids))
    extra_findings = sum(1 for f in result_findings if f["matched_bug_id"] is None)

    return result_findings, len(matched_bug_ids), missed_ids, extra_findings


def lint_design(design_name, examples_dir):
    d_dir = Path(examples_dir) / design_name
    buggy_file = d_dir / "buggy" / f"{design_name}.v"
    if not buggy_file.exists():
        raise FileNotFoundError(f"Buggy file not found: {buggy_file}")

    cmd = _get_verilator_base_cmd() + ["--lint-only", "-Wall", str(buggy_file)]
    res = subprocess.run(cmd, capture_output=True, text=True)
    # Verilator outputs errors and warnings on stderr
    raw_output = res.stderr + "\n" + res.stdout
    findings = parse_verilator_output(raw_output, default_file=f"buggy/{design_name}.v")

    planted_bugs = load_ground_truth(d_dir)
    annotated_findings, detected_count, missed_ids, extra_cnt = match_findings_to_bugs(
        findings, planted_bugs
    )

    return {
        "name": design_name,
        "findings": annotated_findings,
        "planted": len(planted_bugs),
        "detected": detected_count,
        "missed_bug_ids": missed_ids,
        "extra_findings": extra_cnt
    }


def run_all_lint(examples_dir="examples", output_path="results/lint.json"):
    v_ver = get_verilator_version()
    designs = []
    total_planted = 0
    total_detected = 0

    p_examples = Path(examples_dir)
    for d in sorted(p_examples.iterdir()):
        if d.is_dir() and (d / "buggy" / f"{d.name}.v").exists():
            res = lint_design(d.name, examples_dir)
            designs.append(res)
            total_planted += res["planted"]
            total_detected += res["detected"]

    out = {
        "schema_version": 1,
        "verilator_version": v_ver,
        "designs": designs,
        "totals": {
            "planted": total_planted,
            "detected": total_detected
        }
    }

    p_out = Path(output_path)
    p_out.parent.mkdir(parents=True, exist_ok=True)
    with open(p_out, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2)

    return out


REPO_ROOT = Path(__file__).resolve().parent.parent


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _repo_relative(examples_dir, design, file):
    """Repo-relative path with forward slashes, e.g. examples/fifo/buggy/fifo.v."""
    path = Path(examples_dir).resolve() / design / file
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return f"examples/{design}/{file}"


def build_lint_section(lint_data, examples_dir="examples"):
    """Turn the run_all_lint() result into the `lint` section of docs/results_schema.md."""
    warnings = []
    for design in lint_data["designs"]:
        for f in design["findings"]:
            warnings.append({
                "design": design["name"],
                "rule": f["rule"],
                "file": _repo_relative(examples_dir, design["name"], f["file"]),
                "line": f["line"],
                "severity": f["severity"],
                "message": f["message"],
                "matched_bug_id": f["matched_bug_id"],
            })
    return {"generated_at": _now(), "warnings": warnings}


def write_lint_section(results_path, lint_data, examples_dir="examples"):
    """Replace only the `lint` section of results.json and keep every other section.

    A missing file is created. A corrupt file raises RuntimeError and is left untouched.
    """
    path = Path(results_path)
    doc = {}
    if path.exists():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as err:
            raise RuntimeError(f"Cannot update corrupt {path}: {err}") from err
    now = _now()
    doc.setdefault("schema_version", 1)
    doc.setdefault("run", {
        "id": now.replace(":", "-") + "-local",
        "started_at": now,
        "verilator_version": lint_data["verilator_version"],
    })
    doc["lint"] = build_lint_section(lint_data, examples_dir)

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return doc


if __name__ == "__main__":
    # usage: python lint/linter.py [examples_dir] [lint.json] [results.json]
    ex_dir = sys.argv[1] if len(sys.argv) > 1 else "examples"
    out_file = sys.argv[2] if len(sys.argv) > 2 else "results/lint.json"
    results_file = sys.argv[3] if len(sys.argv) > 3 else str(Path(out_file).parent / "results.json")
    data = run_all_lint(ex_dir, out_file)
    print(f"Lint complete: {data['totals']['detected']}/{data['totals']['planted']} planted bugs detected across {len(data['designs'])} design(s).")
    print(f"Results saved to {out_file}")
    try:
        write_lint_section(results_file, data, ex_dir)
    except RuntimeError as err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
    print(f"Updated lint section in {results_file}")
