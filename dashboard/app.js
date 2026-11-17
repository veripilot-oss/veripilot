"use strict";

// VeriPilot dashboard. Reads one results.json (docs/results_schema.md) and shows it.
// Rules it follows from the schema:
//  - A missing section means "stage not run", never zero.
//  - The health score is shown exactly as written in the `health` section. It is not recomputed here.
// All data is inserted with textContent, never as HTML.

const REAL_PATH = "../results/results.json";
const EXAMPLE_PATH = "../examples/results.example.json";
const STAGES = ["lint", "autofix", "regression", "coverage", "triage"];
const STAGE_TITLES = { lint: "Lint", autofix: "Autofix", regression: "Regression", coverage: "Coverage", triage: "Triage" };

const app = document.getElementById("app");
const banner = document.getElementById("banner");
const metaEl = document.getElementById("meta");

function el(tag, opts = {}, ...kids) {
  const n = document.createElement(tag);
  if (opts.cls) n.className = opts.cls;
  if (opts.text !== undefined) n.textContent = String(opts.text);
  if (opts.attrs) for (const [k, v] of Object.entries(opts.attrs)) n.setAttribute(k, v);
  for (const k of kids) if (k) n.append(k);
  return n;
}

function showBanner(msg, isError) {
  banner.hidden = !msg;
  banner.textContent = msg || "";
  banner.className = "banner" + (isError ? " error" : "");
}

const plural = (n, one, many) => `${n} ${n === 1 ? one : many}`;
const pct = (x) => (x === null || x === undefined ? "n/a" : x.toFixed(1) + "%");
const tone = (s) => (s >= 80 ? "good" : s >= 50 ? "warn" : "bad");
const rows = (doc, section, key) => (doc[section] && doc[section][key]) || [];
const byDesign = (list, d) => list.filter((r) => r.design === d);
const lbl = (t) => el("span", { cls: "lbl", text: t + " " });

function designsOf(doc) {
  const set = new Set();
  [["lint", "warnings"], ["autofix", "attempts"], ["regression", "tests"], ["coverage", "designs"], ["triage", "labels"]]
    .forEach(([s, k]) => rows(doc, s, k).forEach((r) => r.design && set.add(r.design)));
  return [...set].sort();
}

/* ---------- verdict ---------- */

function verdictText(doc) {
  const tests = rows(doc, "regression", "tests");
  const labels = rows(doc, "triage", "labels");
  const flaky = labels.filter((l) => l.label === "flaky").length;
  const repeatable = labels.filter((l) => l.label === "repeatable").length;
  const warnings = rows(doc, "lint", "warnings").length;
  const attempts = rows(doc, "autofix", "attempts");
  const verified = attempts.filter((a) => a.verified === true).length;

  let headline;
  if (!doc.regression) headline = "Regression has not run yet";
  else if (!tests.length) headline = "No test runs recorded";
  else {
    const passed = tests.filter((t) => t.status === "pass").length;
    headline = passed === tests.length ? `All ${plural(tests.length, "test run", "test runs")} passed` : `${passed} of ${plural(tests.length, "test run", "test runs")} passed`;
  }

  const bits = [];
  if (doc.triage) bits.push(`${flaky} flaky and ${repeatable} repeatable ${repeatable === 1 && flaky === 0 ? "failure" : "failures"}`);
  if (doc.lint) bits.push(plural(warnings, "lint warning", "lint warnings"));
  if (doc.autofix) bits.push(`${verified} of ${plural(attempts.length, "fix", "fixes")} verified`);
  const detail = bits.length ? bits.join(". ") + "." : "No other stage has reported yet.";
  return { headline, detail };
}

function scoreBlock(doc) {
  const h = doc.health;
  const box = el("div", { cls: "score" });
  if (!h || typeof h.score !== "number") {
    box.append(el("p", { cls: "empty", text: "No health score in this file. Either nothing could be measured or the stage has not run." }));
    return box;
  }
  box.append(el("div", { cls: "score-top" }, el("span", { cls: "score-label", text: "Health score" }), el("span", { cls: "score-num", text: `${h.score.toFixed(1)} / 100` })));
  const fill = el("span");
  fill.style.width = Math.max(0, Math.min(100, h.score)) + "%";
  box.append(el("div", { cls: "meter " + tone(h.score), attrs: { role: "img", "aria-label": `Health score ${h.score.toFixed(1)} out of 100` } }, fill));
  Object.entries(h.components || {}).forEach(([name, v]) => {
    const f = el("span");
    f.style.width = Math.max(0, Math.min(100, v)) + "%";
    box.append(el("div", { cls: "comp" }, el("span", { text: name }), el("div", { cls: "bar" }, f), el("span", { cls: "v", text: v.toFixed(1) })));
  });
  const missing = ["lint", "regression", "coverage", "autofix"].filter((s) => !(h.components && s in h.components));
  if (missing.length) box.append(el("p", { cls: "note", text: "Not measured: " + missing.join(", ") + "." }));
  return box;
}

/* ---------- pipeline strip ---------- */

function stageInfo(doc, s) {
  if (!doc[s]) return { state: "idle", sum: "not run" };
  if (s === "lint") {
    const n = rows(doc, s, "warnings").length;
    return { state: n ? "attn" : "ok", sum: plural(n, "warning", "warnings") };
  }
  if (s === "autofix") {
    const a = rows(doc, s, "attempts");
    const ok = a.filter((x) => x.verified === true).length;
    return { state: a.length && ok < a.length ? "attn" : "ok", sum: `${ok} of ${a.length} verified` };
  }
  if (s === "regression") {
    const t = rows(doc, s, "tests");
    const p = t.filter((x) => x.status === "pass").length;
    return { state: t.length && p < t.length ? "bad" : "ok", sum: `${p} of ${plural(t.length, "run", "runs")} passed` };
  }
  if (s === "coverage") {
    const vals = rows(doc, s, "designs").map((d) => d.line_percent).filter((v) => typeof v === "number");
    if (!vals.length) return { state: "ok", sum: "no data" };
    const lo = Math.min(...vals), hi = Math.max(...vals);
    return { state: "ok", sum: lo === hi ? `${lo.toFixed(1)}% line` : `${lo.toFixed(1)}–${hi.toFixed(1)}% line` };
  }
  const l = rows(doc, s, "labels");
  const f = l.filter((x) => x.label === "flaky").length;
  return { state: l.length ? "attn" : "ok", sum: l.length ? `${f} flaky, ${l.length - f} repeatable` : "no failures" };
}

function pipeline(doc) {
  const ol = el("ol", { cls: "pipeline", attrs: { "aria-label": "Pipeline stages in order" } });
  STAGES.forEach((s) => {
    const info = stageInfo(doc, s);
    ol.append(el("li", { cls: "stage " + info.state }, el("div", { cls: "name" }, el("span", { cls: "dot" }), document.createTextNode(STAGE_TITLES[s])), el("div", { cls: "sum", text: info.sum })));
  });
  return ol;
}

/* ---------- designs ---------- */

function seedStrip(runs) {
  const strip = el("span", { cls: "strip" });
  [...runs].sort((a, b) => a.seed - b.seed).forEach((r, i) => {
    const ok = r.status === "pass";
    const c = el("span", { cls: "seed " + (ok ? "pass" : "fail"), text: ok ? "✓" : "✕", attrs: { role: "img", title: `seed ${r.seed}: ${r.status}, ${r.duration_s}s`, "aria-label": `seed ${r.seed} ${r.status}` } });
    c.style.setProperty("--i", i);
    strip.append(c);
  });
  return strip;
}

function testsCell(doc, d) {
  const cell = el("div", { cls: "tests" });
  if (!doc.regression) return el("div", { cls: "pending", text: "not run" });
  const runs = byDesign(rows(doc, "regression", "tests"), d);
  if (!runs.length) return el("div", { cls: "pending", text: "no runs" });
  const names = [...new Set(runs.map((r) => r.test))];
  names.forEach((name) => {
    const label = byDesign(rows(doc, "triage", "labels"), d).find((l) => l.test === name);
    const line = el("div", { cls: "test" }, el("span", { cls: "tname", text: name }), seedStrip(runs.filter((r) => r.test === name)));
    if (label) line.append(el("span", { cls: "tag " + label.label, text: label.label }));
    cell.append(line);
  });
  return cell;
}

function covCell(doc, d) {
  if (!doc.coverage) return el("div", { cls: "pending", text: "not run" });
  const c = byDesign(rows(doc, "coverage", "designs"), d)[0];
  if (!c) return el("div", { cls: "pending", text: "none" });
  const row = (name, v) => {
    const f = el("span");
    f.style.width = (typeof v === "number" ? Math.max(0, Math.min(100, v)) : 0) + "%";
    return el("div", { cls: "row" }, el("span", { text: name }), el("div", { cls: "bar" }, f), el("span", { cls: "v", text: pct(v) }));
  };
  return el("div", { cls: "cov" }, row("line", c.line_percent), row("toggle", c.toggle_percent));
}

function lintCell(doc, d) {
  if (!doc.lint) return el("div", { cls: "pending", text: "not run" });
  const w = byDesign(rows(doc, "lint", "warnings"), d);
  return el("div", { cls: "cell-lint " + (w.length ? "warn" : "good") }, el("span", { cls: "n", text: w.length }), document.createTextNode(w.length === 1 ? " warning" : " warnings"));
}

function fixCell(doc, d) {
  if (!doc.autofix) return el("div", { cls: "pending", text: "not run" });
  const a = byDesign(rows(doc, "autofix", "attempts"), d);
  if (!a.length) return el("div", { cls: "pending", text: "none" });
  const ok = a.filter((x) => x.verified === true).length;
  return el("div", { cls: ok === a.length ? "good" : "warn", text: `${ok} of ${a.length} verified` });
}

function triageCell(doc, d) {
  if (!doc.triage) return el("div", { cls: "pending", text: "not run" });
  const l = byDesign(rows(doc, "triage", "labels"), d);
  if (!l.length) return el("div", { cls: "pending", text: "no failures" });
  const f = l.filter((x) => x.label === "flaky").length;
  return el("div", { cls: "warn", text: `${f} flaky, ${l.length - f} repeatable` });
}

function simpleTable(headers, body) {
  const tr = el("tr");
  headers.forEach((h) => tr.append(el("th", { text: h })));
  const tbody = el("tbody");
  body.forEach((r) => {
    const row = el("tr");
    r.forEach((c) => row.append(c instanceof Node ? el("td", {}, c) : el("td", { text: c === null || c === undefined ? "" : c })));
    tbody.append(row);
  });
  return el("div", { cls: "tablewrap" }, el("table", {}, el("thead", {}, tr), tbody));
}

function detailPanel(doc, d) {
  const panel = el("div", { cls: "panel" });
  const block = (title, node) => panel.append(el("section", {}, el("h3", { text: title }), node));

  if (doc.lint) {
    const w = byDesign(rows(doc, "lint", "warnings"), d);
    block("Lint warnings", w.length
      ? simpleTable(["Rule", "Where", "Message", "Planted bug"], w.map((x) => [el("code", { text: x.rule }), el("code", { text: `${x.file}:${x.line}` }), x.message, x.matched_bug_id == null ? "" : `#${x.matched_bug_id}`]))
      : el("p", { cls: "empty", text: "No warnings for this design." }));
  }
  if (doc.autofix) {
    const a = byDesign(rows(doc, "autofix", "attempts"), d);
    const wrap = el("div");
    if (!a.length) wrap.append(el("p", { cls: "empty", text: "No fix attempts for this design." }));
    a.forEach((x) => {
      const diff = el("div", { cls: "diff" });
      diff.append(el("div", { cls: "del", text: "− " + (x.before || "") }));
      diff.append(el("div", { cls: "add", text: "+ " + (x.after === "" ? "(line removed)" : x.after) }));
      wrap.append(el("div", { cls: "fix" },
        el("div", { cls: "head" }, el("code", { text: x.rule }), el("code", { text: `${x.file}:${x.line}` }), el("span", { cls: "tag " + (x.verified ? "verified" : "unverified"), text: x.verified ? "verified" : "not verified" }), el("span", { text: x.note || "" })),
        diff));
    });
    block("Autofix attempts", wrap);
  }
  if (doc.regression) {
    const r = byDesign(rows(doc, "regression", "tests"), d);
    block("Regression runs", r.length
      ? simpleTable(["Test", "Seed", "Status", "Seconds"], r.map((x) => [el("code", { text: x.test }), x.seed, x.status, x.duration_s]))
      : el("p", { cls: "empty", text: "No runs for this design." }));
  }
  return panel;
}

function designsSection(doc) {
  const designs = designsOf(doc);
  const sec = el("section");
  sec.append(el("h2", { cls: "section-title", text: "Designs" }));
  if (!designs.length) {
    sec.append(el("p", { cls: "empty", text: "No design has results yet. Run the pipeline, then reload." }));
    return sec;
  }
  const box = el("div", { cls: "designs" });
  const cols = el("div", { cls: "cols" });
  ["Design", "Lint", "Tests by seed", "Coverage", "Autofix", "Triage"].forEach((c) => cols.append(el("span", { text: c })));
  box.append(cols);
  designs.forEach((d) => {
    const det = el("details", { cls: "design" });
    const sum = el("summary");
    sum.append(el("span", { cls: "dname", text: d }));
    [["Lint", lintCell], ["Tests", testsCell], ["Coverage", covCell], ["Autofix", fixCell], ["Triage", triageCell]].forEach(([label, make]) => {
      const c = make(doc, d);
      c.prepend(lbl(label));
      sum.append(c);
    });
    det.append(sum, detailPanel(doc, d));
    box.append(det);
  });
  sec.append(box);
  return sec;
}

/* ---------- page ---------- */

function render(doc, sourceNote) {
  app.replaceChildren();
  metaEl.textContent = "";
  if (!doc || typeof doc !== "object" || typeof doc.schema_version !== "number") {
    showBanner("This file does not look like a VeriPilot results.json: it has no schema_version.", true);
    return;
  }
  const run = doc.run || {};
  metaEl.textContent = [sourceNote, run.id && `run ${run.id}`, run.verilator_version && `Verilator ${run.verilator_version}`, run.git_sha && `commit ${run.git_sha}`].filter(Boolean).join("  |  ");

  const v = verdictText(doc);
  app.append(el("section", { cls: "verdict" },
    el("div", {}, el("h2", { text: v.headline }), el("p", { cls: "detail", text: v.detail })),
    scoreBlock(doc)));
  app.append(pipeline(doc));
  app.append(designsSection(doc));
}

async function loadFrom(path) {
  const res = await fetch(path, { cache: "no-store" });
  if (!res.ok) throw new Error(`${path}: HTTP ${res.status}`);
  return res.json();
}

async function loadDefault() {
  try {
    render(await loadFrom(REAL_PATH), "results/results.json");
    showBanner("");
    return;
  } catch (e) { /* fall back to the example */ }
  try {
    render(await loadFrom(EXAMPLE_PATH), "example data");
    showBanner("Showing example (mock) data because results/results.json was not found. Run the pipeline, or open a file.", false);
  } catch (e) {
    app.replaceChildren();
    showBanner("Could not load any data. If you opened this page straight from disk, serve the repo instead: run python3 -m http.server from the repo root and open /dashboard/. Or use Open results.json.", true);
  }
}

function loadFile(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      render(JSON.parse(reader.result), file.name);
      showBanner("");
    } catch (e) {
      app.replaceChildren();
      showBanner(`Could not read ${file.name}: ${e.message}`, true);
    }
  };
  reader.readAsText(file);
}

document.getElementById("file").addEventListener("change", (e) => e.target.files[0] && loadFile(e.target.files[0]));
document.getElementById("example").addEventListener("click", async () => {
  try {
    render(await loadFrom(EXAMPLE_PATH), "example data");
    showBanner("Showing example (mock) data.", false);
  } catch (e) {
    showBanner("Could not load the example. Serve the repo over http, or use Open results.json.", true);
  }
});
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => {
  e.preventDefault();
  if (e.dataTransfer.files[0]) loadFile(e.dataTransfer.files[0]);
});

loadDefault();
