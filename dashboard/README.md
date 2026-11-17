# dashboard

A static page that shows `results/results.json`. No build step and no dependencies: `index.html`, `style.css`, `app.js`.

## Run it

From the repo root:

```bash
python3 -m http.server 8000
```

Then open <http://localhost:8000/dashboard/>.

The page loads `results/results.json` if it exists. If not, it falls back to `examples/results.example.json` and shows a banner saying it is mock data. You can also use **Open results.json** or drag a file onto the page, which works even when the page is opened straight from disk.

## What it shows

- **Verdict**: a plain sentence such as "2 of 3 test runs passed", plus counts of flaky and repeatable failures, lint warnings and verified fixes. All counts come straight from the file.
- **Health score**: the `health` section exactly as written, with its components. The page does not recompute it. The formula lives in `health/score.py`. The colour of the meter (green from 80, amber from 50) is display only.
- **Pipeline strip**: lint, autofix, regression, coverage and triage in order. A stage that has not run is hatched and says "not run".
- **One row per design** (`fifo`, `spi`, `timer`): lint, tests, coverage, autofix and triage. Tests are shown as a **seed strip**, one cell per seed (tick = pass, cross = fail), so a flaky test (mixed cells) is easy to tell from a repeatable failure (all crosses). Click a row for the lint warnings, the autofix before and after, the per-seed runs, and the triage labels (flaky or repeatable, with failed runs out of total). Triage labels are listed even for a test that has no regression runs, such as the demo tests.

A missing section means that stage has not run. The page shows "not run", never zero. See `docs/results_schema.md`.
