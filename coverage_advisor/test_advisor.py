import json
import re
import tempfile
import unittest
from pathlib import Path
from coverage_advisor.advisor import parse_annotated_coverage, is_declaration_line, update_results_json


TS_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


def validate_results_doc(doc: dict) -> list[str]:
    """Lightweight stdlib validator mirroring tests/test_results_schema.py."""
    errs = []
    if not isinstance(doc, dict):
        return ["top level must be an object"]
    if doc.get("schema_version") != 1:
        errs.append("schema_version must be 1")
    run = doc.get("run")
    if not isinstance(run, dict):
        errs.append("run is required")
    else:
        if not TS_PATTERN.match(run.get("started_at", "")):
            errs.append("run.started_at must be UTC ISO 8601")
    cov = doc.get("coverage")
    if cov:
        if not TS_PATTERN.match(cov.get("generated_at", "")):
            errs.append("coverage.generated_at must be UTC ISO 8601")
        designs = cov.get("designs")
        if not isinstance(designs, list):
            errs.append("coverage.designs must be a list")
        else:
            for i, d in enumerate(designs):
                if not isinstance(d.get("design"), str):
                    errs.append(f"designs[{i}].design must be str")
                lp = d.get("line_percent")
                if not isinstance(lp, (int, float)) or not (0 <= lp <= 100):
                    errs.append(f"designs[{i}].line_percent invalid")
    return errs


class TestCoverageAdvisor(unittest.TestCase):
    def test_is_declaration_line(self):
        self.assertTrue(is_declaration_line("input wire reset,"))
        self.assertTrue(is_declaration_line("output wire [7:0] data_out,"))
        self.assertTrue(is_declaration_line("wire clk;"))
        self.assertTrue(is_declaration_line("reg [15:0] counter;"))
        self.assertTrue(is_declaration_line("localparam IDLE=2'b00;"))
        self.assertTrue(is_declaration_line("module fifo;"))
        self.assertTrue(is_declaration_line("endmodule"))
        self.assertTrue(is_declaration_line("// comments"))
        self.assertFalse(is_declaration_line("state <= IDLE;"))
        self.assertFalse(is_declaration_line("if (start) begin"))
        self.assertFalse(is_declaration_line("assign done = (state == DONE);"))

    def test_parse_annotated_coverage(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            repo_root = tmp_path
            examples_dir = repo_root / "examples" / "fifo" / "golden"
            examples_dir.mkdir(parents=True, exist_ok=True)
            rtl_file = examples_dir / "fifo.v"
            annotated_dir = repo_root / "annotated"
            annotated_dir.mkdir(parents=True, exist_ok=True)
            annotated_file = annotated_dir / "fifo.v"

            content = (
                " 000005 module fifo;\n"
                "%000000   input wire reset,\n"  # should be filtered as declaration
                "%000000   reg error_flag;\n"   # should be filtered as declaration
                " 000010   always @(posedge clk) begin\n"
                "######     state <= NEXT;\n"     # uncovered statement/branch
                " 000002   end\n"
                "endmodule\n"
            )
            annotated_file.write_text(content, encoding="utf-8")

            pct, uncovered = parse_annotated_coverage(annotated_dir, rtl_file, repo_root=repo_root)
            self.assertGreater(pct, 0)
            self.assertEqual(len(uncovered), 1)
            self.assertEqual(uncovered[0]["line"], 5)
            self.assertEqual(uncovered[0]["file"], "examples/fifo/golden/fifo.v")
            self.assertIn("state <= NEXT;", uncovered[0]["code"])

    def test_update_results_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res_file = Path(tmpdir) / "results" / "results.json"
            coverage_summary = {
                "fifo": {"covered_percent": 100.0, "uncovered": []},
                "spi": {"covered_percent": 88.0, "uncovered": [{"file": "examples/spi/golden/spi.v", "line": 40, "kind": "line", "code": "foo"}]}
            }
            update_results_json(coverage_summary, res_file)
            self.assertTrue(res_file.exists())

            doc = json.loads(res_file.read_text(encoding="utf-8"))
            errs = validate_results_doc(doc)
            self.assertEqual(errs, [])
            self.assertIn("coverage", doc)
            self.assertEqual(len(doc["coverage"]["designs"]), 2)
            self.assertEqual(doc["coverage"]["designs"][0]["design"], "fifo")
            self.assertEqual(doc["coverage"]["designs"][0]["line_percent"], 100.0)

    def test_update_results_json_corrupt_file_raises_runtime_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            res_file = Path(tmpdir) / "results" / "results.json"
            res_file.parent.mkdir(parents=True, exist_ok=True)
            # Write invalid JSON content
            res_file.write_text("{ corrupt json content", encoding="utf-8")

            coverage_summary = {"fifo": {"covered_percent": 100.0, "uncovered": []}}
            with self.assertRaises(RuntimeError) as ctx:
                update_results_json(coverage_summary, res_file)
            self.assertIn("Cannot update corrupt", str(ctx.exception))

        with tempfile.TemporaryDirectory() as tmpdir:
            res_file = Path(tmpdir) / "results" / "results.json"
            res_file.parent.mkdir(parents=True, exist_ok=True)
            # Write non-dict JSON content (e.g. JSON array)
            res_file.write_text("[1, 2, 3]", encoding="utf-8")

            coverage_summary = {"fifo": {"covered_percent": 100.0, "uncovered": []}}
            with self.assertRaises(RuntimeError) as ctx:
                update_results_json(coverage_summary, res_file)
            self.assertIn("Cannot update corrupt", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
