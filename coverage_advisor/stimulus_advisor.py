"""Rule-Based Stimulus Synthesis Scaffolding for VeriPilot coverage advisor.

Analyzes uncovered statements and branches from coverage_advisor reports
and synthesizes targeted Verilog test stimulus to exercise uncovered lines.

Architecture & Extension Note:
The `generate_targeted_stimulus` function analyzes uncovered source context
using deterministic heuristic rules. It serves as the plug-in interface where
an external LLM model or agent can be attached to generate novel stimulus.
In current designs (such as SPI and Timer), defensive `default` case branches
in 2-bit FSMs represent unreachable ceilings (83.33% and 95.83%) when all
valid states are already exercised.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List

# Ensure repository root is on sys.path so the module runs without PYTHONPATH=.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from coverage_advisor.advisor import run_design_coverage


def extract_uncovered_context(uncovered_list: list[dict[str, Any]]) -> str:
    """Build a readable context string containing the uncovered code lines with line numbers."""
    if not uncovered_list:
        return "No uncovered lines."

    lines = []
    for item in uncovered_list:
        line_no = item.get("line", "?")
        code = item.get("code", "").strip()
        lines.append(f"Line {line_no}: {code}")
    return "\n".join(lines)


def generate_targeted_stimulus(design_name: str, uncovered_items: list[dict[str, Any]]) -> str:
    """Synthesize testbench stimulus sequences targeting uncovered RTL context.

    Analyzes uncovered source context dynamically rather than relying on fixed
    line numbers. Serves as the extension point where an external LLM
    can be plugged in.

    When coverage_advisor.llm_stimulus is available (i.e. llm_client has been
    installed), it is tried first.  On any failure the function falls back to
    the deterministic rule-based heuristics below.
    """
    if not uncovered_items:
        return ""

    # --- LLM path (optional, falls back gracefully) -------------------------
    try:
        from coverage_advisor import llm_stimulus as _llm_stim  # type: ignore[import]
        llm_result = _llm_stim.generate(design_name, uncovered_items)
        if llm_result is not None:
            return llm_result
    except ImportError:
        pass
    # ------------------------------------------------------------------------

    context = extract_uncovered_context(uncovered_items)
    stimulus_blocks: list[str] = []

    # Heuristic 1: Uncovered case/default state transitions
    has_default_or_state = bool(
        re.search(r"\bdefault\b", context, re.IGNORECASE)
        or re.search(r"\bstate\b", context, re.IGNORECASE)
        or re.search(r"\bcase\b", context, re.IGNORECASE)
    )

    # Heuristic 2: Uncovered counter or timer boundary conditions
    has_counter_or_timer = bool(
        re.search(r"\bcounter\b", context, re.IGNORECASE)
        or re.search(r"\bcount\b", context, re.IGNORECASE)
        or re.search(r"\btimer\b", context, re.IGNORECASE)
    )

    # Heuristic 3: Uncovered FIFO full/empty boundaries
    has_fifo_boundary = bool(
        re.search(r"\bfull\b", context, re.IGNORECASE)
        or re.search(r"\bempty\b", context, re.IGNORECASE)
        or re.search(r"\bwr_ptr\b|\brd_ptr\b", context, re.IGNORECASE)
    )

    if design_name == "spi":
        if has_default_or_state:
            stimulus_blocks.append("""
    // [Stimulus Synthesis] Exercise SPI state machine transitions and corner values
    @(negedge clk);
    start = 1'b0;
    repeat (2) @(posedge clk);
    do_xfer(8'h00, 8'h00);
    do_xfer(8'hFF, 8'hFF);
    repeat (2) @(posedge clk);
""")

    elif design_name == "timer":
        if has_counter_or_timer or has_default_or_state:
            stimulus_blocks.append("""
    // [Stimulus Synthesis] Exercise timer zero-count and boundary edge conditions
    drive(1, 16'd0);
    repeat (3) @(negedge clk);
    drive(0, 16'd0);
    repeat (5) @(negedge clk);
""")

    elif design_name == "fifo":
        if has_fifo_boundary or has_default_or_state:
            stimulus_blocks.append("""
    // [Stimulus Synthesis] Exercise FIFO boundary limits (overflow and underflow attempts)
    repeat (2) @(negedge clk);
    // Write until full + 1 extra write attempt
    repeat (18) begin
        @(negedge clk);
        wr_en = 1'b1;
        din = $urandom_range(0, 255);
    end
    @(negedge clk);
    wr_en = 1'b0;
    // Read until empty + 1 extra read attempt
    repeat (18) begin
        @(negedge clk);
        rd_en = 1'b1;
    end
    @(negedge clk);
    rd_en = 1'b0;
    repeat (2) @(posedge clk);
""")

    return "\n".join(stimulus_blocks)


def patch_testbench_content(original_content: str, stimulus_code: str) -> str:
    """Insert synthetic stimulus before the final checks without altering existing tests."""
    marker = "if (error == 0)"
    if marker in original_content:
        parts = original_content.split(marker, 1)
        return parts[0] + stimulus_code + "\n    " + marker + parts[1]

    if "$finish;" in original_content:
        parts = original_content.rsplit("$finish;", 1)
        return parts[0] + stimulus_code + "\n    $finish;" + parts[1]

    return original_content + "\n" + stimulus_code


def evaluate_stimulus_in_sandbox(design_name: str, repo_root: Path) -> dict[str, Any]:
    """Evaluate synthesized stimulus in an isolated temporary sandbox.

    IMPORTANT: Never modifies any files under examples/ in the committed repository.
    All builds, patches, and simulations run inside a temporary copy.
    """
    example_dir = repo_root / "examples" / design_name
    golden_rtl = example_dir / "golden" / f"{design_name}.v"
    tb_file = example_dir / f"tb_{design_name}.v"

    if not golden_rtl.exists() or not tb_file.exists():
        raise FileNotFoundError(f"Missing RTL or testbench for design '{design_name}' at {example_dir}")

    # 1. Baseline coverage on unmodified repository
    baseline_rep = run_design_coverage(design_name, repo_root)
    base_cov = baseline_rep.get("covered_percent", 0.0)
    uncovered = baseline_rep.get("uncovered", [])

    if not uncovered or base_cov >= 100.0:
        return {
            "design": design_name,
            "baseline_percent": base_cov,
            "final_percent": base_cov,
            "status": "already_clean",
            "improved": False,
            "uncovered_count": len(uncovered)
        }

    # 2. Synthesize stimulus from uncovered context
    stimulus = generate_targeted_stimulus(design_name, uncovered)
    if not stimulus.strip():
        return {
            "design": design_name,
            "baseline_percent": base_cov,
            "final_percent": base_cov,
            "status": "no_stimulus_generated",
            "improved": False,
            "uncovered_count": len(uncovered)
        }

    # 3. Create isolated sandbox to evaluate patched testbench
    with tempfile.TemporaryDirectory() as tmpdir:
        sandbox_root = Path(tmpdir)
        sandbox_examples = sandbox_root / "examples" / design_name
        sandbox_golden = sandbox_examples / "golden"
        sandbox_golden.mkdir(parents=True, exist_ok=True)

        # Copy design and testbench to sandbox
        shutil.copy2(golden_rtl, sandbox_golden / f"{design_name}.v")
        orig_tb = tb_file.read_text(encoding="utf-8")
        patched_tb = patch_testbench_content(orig_tb, stimulus)
        (sandbox_examples / f"tb_{design_name}.v").write_text(patched_tb, encoding="utf-8")

        # 4. Measure coverage on sandbox copy
        try:
            patched_rep = run_design_coverage(design_name, sandbox_root)
            new_cov = patched_rep.get("covered_percent", 0.0)
            new_uncovered = patched_rep.get("uncovered", [])

            if new_cov > base_cov:
                return {
                    "design": design_name,
                    "baseline_percent": base_cov,
                    "final_percent": new_cov,
                    "status": "improved",
                    "improved": True,
                    "uncovered_count": len(new_uncovered)
                }
            else:
                return {
                    "design": design_name,
                    "baseline_percent": base_cov,
                    "final_percent": base_cov,
                    "status": "no_coverage_increase",
                    "improved": False,
                    "uncovered_count": len(uncovered)
                }
        except Exception as e:
            return {
                "design": design_name,
                "baseline_percent": base_cov,
                "final_percent": base_cov,
                "status": f"failed: {e}",
                "improved": False,
                "uncovered_count": len(uncovered)
            }


def update_results_json(stimulus_summary: dict[str, Any], results_path: Path) -> None:
    """Update or create results/results.json with the stimulus section.

    Adheres to the shared results_schema.md writer rules:
    - Writes only its own section ('stimulus') and leaves other sections untouched.
    - If the file exists but is corrupt / not valid JSON / not a dict, raises RuntimeError.
    - Generates UTC ISO 8601 timestamp ending in 'Z'.
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

    doc["stimulus"] = {
        "generated_at": now_iso,
        "designs": stimulus_summary.get("designs", [])
    }

    results_path.parent.mkdir(parents=True, exist_ok=True)
    with open(results_path, "w", encoding="utf-8") as f:
        json.dump(doc, f, indent=2)


def run_all_stimulus_synthesis(
    designs: list[str],
    repo_root: Path,
    out_file: Path | None = None,
    results_path: Path | None = None
) -> dict[str, Any]:
    """Run stimulus synthesis across designs and output summary results."""
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    results = []

    for d in designs:
        print(f"[*] Evaluating stimulus synthesis for {d}...")
        try:
            res = evaluate_stimulus_in_sandbox(d, repo_root)
            results.append(res)
            print(f"[+] {d}: baseline {res['baseline_percent']}%, final {res['final_percent']}% -> {res['status']}")
        except Exception as e:
            print(f"[-] Error evaluating {d}: {e}")
            results.append({
                "design": d,
                "baseline_percent": 0.0,
                "final_percent": 0.0,
                "status": f"error: {e}",
                "improved": False,
                "uncovered_count": 0
            })

    report = {
        "generated_at": now_iso,
        "designs": results
    }

    if out_file:
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)

    if results_path:
        update_results_json(report, results_path)

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="VeriPilot Rule-Based Stimulus Synthesis Advisor")
    parser.add_argument("designs", nargs="*", default=["fifo", "spi", "timer"], help="Designs to evaluate")
    parser.add_argument(
        "--out-file",
        default="coverage_advisor/reports/stimulus_report.json",
        help="Path to output JSON report"
    )
    parser.add_argument(
        "--results-json",
        default="results/results.json",
        help="Path to unified results.json file"
    )
    args = parser.parse_args()

    root = REPO_ROOT
    out_path = root / args.out_file if args.out_file else None
    results_path = root / args.results_json if args.results_json else None
    run_all_stimulus_synthesis(args.designs, root, out_path, results_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
