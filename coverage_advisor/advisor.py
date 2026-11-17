#!/usr/bin/env python3
"""Coverage Advisor for VeriPilot.

Builds designs with Verilator --coverage, executes testbenches, parses
line and toggle coverage from verilator_coverage annotations, and generates
standardized JSON reports.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List


def is_declaration_line(code: str) -> bool:
    """Return True if a line is a declaration or structural definition rather than an executable statement/branch."""
    stripped = code.strip()
    if not stripped or stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return True

    # Declaration keywords at start of line
    decl_patterns = [
        r"^(?:input|output|inout)\b",
        r"^(?:wire|reg|integer|real|time)\b",
        r"^(?:parameter|localparam)\b",
        r"^(?:module|endmodule)\b",
        r"^(?:`default_nettype|`timescale|`include|`define|`ifdef|`ifndef|`endif)\b",
    ]
    for pat in decl_patterns:
        if re.search(pat, stripped):
            return True

    # Port list lines (e.g. "input wire reset," or "[7:0] data_in,")
    if re.match(r"^(?:input|output|inout|wire|reg|\w+)?\s*(?:\[[^\]]+\])?\s*\w+\s*[,;)]", stripped):
        if any(kw in stripped for kw in ["input", "output", "inout", "wire", "reg", "parameter", "localparam"]):
            return True

    return False


def parse_annotated_coverage(annotated_dir: Path, source_file: Path, repo_root: Path | None = None) -> tuple[float, list[dict[str, Any]]]:
    """Parse Verilator annotated coverage file to extract coverage stats and uncovered lines.
    
    Filters out port declarations and structural keywords so only actual statement
    and branch lines are reported as uncovered.
    Uses repo-root-relative path for the 'file' field.
    """
    annotated_file = annotated_dir / source_file.name
    if not annotated_file.exists():
        # Fallback: search for any annotated file matching source name
        candidates = list(annotated_dir.glob(f"*{source_file.name}*"))
        if candidates:
            annotated_file = candidates[0]
        else:
            return 0.0, []

    # Compute relative file path to repo root if possible
    if repo_root:
        try:
            rel_file_path = source_file.resolve().relative_to(repo_root.resolve()).as_posix()
        except Exception:
            rel_file_path = source_file.as_posix()
    else:
        rel_file_path = source_file.as_posix()

    uncovered: list[dict[str, Any]] = []
    total_points = 0
    covered_points = 0

    # Pattern for verilator annotation lines:
    # Example format:
    # %000000   wire foo;  (0 hits)
    #  000010   wire bar;  (10 hits)
    #  ######   uncovered branch/statement
    line_num = 0
    with open(annotated_file, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line_num += 1
            match = re.match(r"^\s*([%#]?\d+|######)\s+(.*)$", line)
            if match:
                prefix = match.group(1).strip()
                code_text = match.group(2).strip()
                
                # Check if it's a declaration/port definition that shouldn't be counted as an uncovered statement/branch gap
                is_decl = is_declaration_line(code_text)

                if prefix.startswith("%") or prefix == "######" or prefix == "0" or prefix == "%000000":
                    if not is_decl:
                        total_points += 1
                        uncovered.append({
                            "file": rel_file_path,
                            "line": line_num,
                            "kind": "line_or_branch",
                            "code": code_text
                        })
                elif prefix.isdigit() and int(prefix) > 0:
                    total_points += 1
                    covered_points += 1

    percent = (covered_points / total_points * 100.0) if total_points > 0 else 100.0
    return round(percent, 2), uncovered


def _resolve_tool_cmd(tool_name: str) -> list[str]:
    """Resolve a tool executable (e.g. 'verilator' or 'verilator_coverage') across Linux and Windows.
    On Windows native Python, shutil.which('verilator') returns None because the Perl script
    has no .exe extension. Scans PATH for an extensionless script and runs it with Perl.
    """
    # 1. Standard which lookup (works on Linux or Windows when .exe/.bat exists)
    found = shutil.which(tool_name)
    if found and (found.endswith(".exe") or found.endswith(".bat") or found.endswith(".cmd")):
        return [found]

    # 2. Scan PATH for extensionless file or perl script
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    for d in path_dirs:
        d = d.strip('"')
        candidate = os.path.join(d, tool_name)
        if os.path.isfile(candidate):
            if sys.platform.startswith("win") or os.name == "nt":
                perl = shutil.which("perl") or "perl"
                return [perl, candidate]
            return [candidate]

    # 3. Fallbacks
    if sys.platform.startswith("win") or os.name == "nt":
        perl = shutil.which("perl") or "perl"
        return [perl, tool_name]
    return [tool_name]


def run_design_coverage(design_name: str, root_dir: Path) -> dict[str, Any]:
    """Build, execute, and analyze coverage for a given example design."""
    example_dir = root_dir / "examples" / design_name
    golden_dir = example_dir / "golden"
    golden_rtl = golden_dir / f"{design_name}.v"
    tb_file = example_dir / f"tb_{design_name}.v"

    if not golden_rtl.exists() or not tb_file.exists():
        raise FileNotFoundError(f"Missing RTL or testbench for design '{design_name}' at {example_dir}")

    obj_dir = example_dir / "obj_dir"
    annotate_dir = example_dir / "annotated"
    coverage_dat = example_dir / "coverage.dat"

    # Clean previous artifacts
    if obj_dir.exists():
        shutil.rmtree(obj_dir)
    if annotate_dir.exists():
        shutil.rmtree(annotate_dir)
    if coverage_dat.exists():
        coverage_dat.unlink()

    top_module = f"tb_{design_name}"

    # 1. Compile with Verilator including -CFLAGS -std=gnu++17
    verilator_bin = _resolve_tool_cmd("verilator")
    build_cmd = verilator_bin + [
        "--binary",
        "--timing",
        "--coverage",
        "-Wno-fatal",
        "-CFLAGS",
        "-std=gnu++17",
        "--top-module",
        top_module,
        "--Mdir",
        str(obj_dir),
        str(golden_rtl),
        str(tb_file)
    ]
    res_build = subprocess.run(build_cmd, cwd=example_dir, capture_output=True, text=True)
    if res_build.returncode != 0:
        err_msg = res_build.stderr.strip() or res_build.stdout.strip()
        raise RuntimeError(f"Verilator build failed for {design_name} (code {res_build.returncode}):\n{err_msg}")

    # 2. Run simulation binary
    exe_name = f"V{top_module}"
    if os.name == "nt" or sys.platform.startswith("win"):
        exe_path = obj_dir / f"{exe_name}.exe"
    else:
        exe_path = obj_dir / exe_name

    res_sim = subprocess.run([str(exe_path)], cwd=example_dir, capture_output=True, text=True)
    if res_sim.returncode != 0:
        err_msg = res_sim.stderr.strip() or res_sim.stdout.strip()
        raise RuntimeError(f"Simulation execution failed for {design_name} (code {res_sim.returncode}):\n{err_msg}")

    # 3. Annotate coverage
    annotate_dir.mkdir(parents=True, exist_ok=True)
    cov_bin = _resolve_tool_cmd("verilator_coverage")
    cov_cmd = cov_bin + [
        "--annotate",
        str(annotate_dir),
        str(coverage_dat)
    ]
    res_cov = subprocess.run(cov_cmd, cwd=example_dir, capture_output=True, text=True)
    if res_cov.returncode != 0:
        err_msg = res_cov.stderr.strip() or res_cov.stdout.strip()
        raise RuntimeError(f"verilator_coverage failed for {design_name} (code {res_cov.returncode}):\n{err_msg}")

    # 4. Parse annotated coverage with relative paths and declaration filtering
    covered_pct, uncovered = parse_annotated_coverage(annotate_dir, golden_rtl, repo_root=root_dir)

    # Clean up non-tracked artifacts
    if obj_dir.exists():
        shutil.rmtree(obj_dir)
    if annotate_dir.exists():
        shutil.rmtree(annotate_dir)
    if coverage_dat.exists():
        coverage_dat.unlink()

    return {
        "name": design_name,
        "covered_percent": covered_pct,
        "uncovered": uncovered
    }


def update_results_json(coverage_summary: dict[str, Any], results_path: Path) -> None:
    """Update or create results/results.json with the coverage section according to results_schema.md.
    
    Adheres to the writers' rules:
    - Writes only its own section ('coverage') and leaves other sections untouched.
    - If the file exists but is corrupt / not valid JSON / not a dict, raises RuntimeError.
    - Generates UTC ISO 8601 timestamp ending in 'Z'.
    - Formats coverage designs as flat list with 'design', 'line_percent', and 'toggle_percent'.
    """
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if results_path.exists():
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception as e:
            raise RuntimeError(f"Cannot update corrupt {results_path}: {e}")
        if not isinstance(doc, dict):
            raise RuntimeError(f"Cannot update corrupt {results_path}: expected JSON object at top level")
    else:
        doc = {}

    if "schema_version" not in doc:
        doc["schema_version"] = 1

    if "run" not in doc:
        doc["run"] = {
            "id": f"{now_iso}-local",
            "started_at": now_iso,
            "verilator_version": "5.034"
        }

    designs_list = []
    for d_name, rep in sorted(coverage_summary.items()):
        designs_list.append({
            "design": d_name,
            "line_percent": rep.get("covered_percent", 0.0),
            "toggle_percent": None
        })

    doc["coverage"] = {
        "generated_at": now_iso,
        "designs": designs_list
    }

    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriPilot Coverage Advisor")
    parser.add_argument("designs", nargs="*", default=["fifo", "spi", "timer"], help="Design names to evaluate")
    parser.add_argument("--out-dir", default="coverage_advisor/reports", help="Output directory for JSON reports")
    parser.add_argument("--results-json", default="results/results.json", help="Path to unified results.json")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
    had_error = False
    for d in args.designs:
        print(f"[*] Running coverage analysis on {d}...")
        try:
            report = run_design_coverage(d, root)
            summary[d] = report
            out_file = out_dir / f"{d}_coverage.json"
            with open(out_file, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
            print(f"[+] {d}: {report['covered_percent']}% covered ({len(report['uncovered'])} uncovered points) -> {out_file}")
        except Exception as e:
            had_error = True
            print(f"[-] Error evaluating {d}: {e}")

    # Emit to unified results.json if we gathered coverage for at least one design
    if summary:
        results_file = root / args.results_json
        try:
            update_results_json(summary, results_file)
            print(f"[+] Updated coverage section in {results_file}")
        except RuntimeError as e:
            print(f"[-] Error writing {results_file}: {e}")
            return 2

    return 1 if had_error else 0


if __name__ == "__main__":
    sys.exit(main())

