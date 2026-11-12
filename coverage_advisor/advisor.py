#!/usr/bin/env python3
"""Coverage Advisor for VeriPilot.

Builds designs with Verilator --coverage, executes testbenches, parses
line and toggle coverage from verilator_coverage annotations, and generates
standardized JSON reports.
"""

from __future__ import annotations

import argparse
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
    build_cmd = [
        "verilator",
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
    subprocess.run(build_cmd, check=True, cwd=example_dir, capture_output=True, text=True)

    # 2. Run simulation binary
    exe_name = f"V{top_module}"
    if os.name == "nt" or sys.platform.startswith("win"):
        exe_path = obj_dir / f"{exe_name}.exe"
    else:
        exe_path = obj_dir / exe_name

    subprocess.run([str(exe_path)], check=True, cwd=example_dir, capture_output=True, text=True)

    # 3. Annotate coverage
    annotate_dir.mkdir(parents=True, exist_ok=True)
    cov_cmd = [
        "verilator_coverage",
        "--annotate",
        str(annotate_dir),
        str(coverage_dat)
    ]
    subprocess.run(cov_cmd, check=True, cwd=example_dir, capture_output=True, text=True)

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


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriPilot Coverage Advisor")
    parser.add_argument("designs", nargs="*", default=["fifo", "spi", "timer"], help="Design names to evaluate")
    parser.add_argument("--out-dir", default="coverage_advisor/reports", help="Output directory for JSON reports")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    summary = {}
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
            print(f"[-] Error evaluating {d}: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(main())

