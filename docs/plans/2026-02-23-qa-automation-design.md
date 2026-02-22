# DGS QA Automation Design

**Date:** 2026-02-23
**Branch:** `qa/automated-inspection`
**Approach:** IPC-driven automated testing with Claude Vision analysis

---

## Goal

Systematically verify that all DGS features work correctly across all 10 test datasets,
using automated IPC interaction + screenshot capture + Claude Vision analysis.
Issues found are fixed immediately and committed.

---

## Architecture

```
[tools/dgs_qa_runner.py]
    ↓ subprocess.Popen
[DGS process]
    ↓↑ asyncio TCP IPC
[QA Runner: scenario loop]
    ↓ capture command
[screenshots/ per dataset]
    ↓ Claude Vision reads images
[analysis + bug detection]
    ↓
[docs/qa/YYYY-MM-DD-qa-report.md]
[bug fix commits]
```

---

## New IPC Commands

| Command | Parameters | Purpose |
|---------|-----------|---------|
| `load_file` | `path: str` | Load a data file into DGS |
| `apply_filter` | `column: str, op: str, value: Any` | Apply a filter condition |
| `clear_filters` | — | Remove all active filters |
| `set_chart_type` | `chart_type: str` | Change the active chart type |
| `get_state` | — | Dump current app state to JSON |

---

## Test Datasets

| File | Type | Key features to test |
|------|------|----------------------|
| 01_sales_simple.csv | Numeric + categorical | Bar chart, grouping, filters |
| 02_stock_ohlc.csv | Time series | Line chart, date filters |
| 03_sensors_timeseries.csv | Time series, multi-column | Line chart, streaming sim |
| 04_employees.csv | Categorical heavy | Grouping, stat panel |
| 05_products_inventory.csv | Numeric + categorical | Filters, summary panel |
| 06_website_analytics.csv | Mixed | Dashboard panel |
| 07_survey_results.csv | Categorical | Distribution, stat panel |
| 08_weather_data.csv | Time series | Line/scatter, date range filter |
| 09_ecommerce_orders.csv | Mixed, large-ish | Performance, table panel |
| 10_bigdata_sample.csv | Large | Performance, progressive loading |

---

## Test Scenario Per Dataset

1. **Load** → `load_file(path)` → full capture (all panels)
2. **Filter** → `apply_filter(col, "eq", val)` → capture graph + table
3. **Chart types** → `set_chart_type("bar")` / `"line"` / `"scatter"` → capture each
4. **Stat panel** → focus stat_panel → capture
5. **State dump** → `get_state()` → record to JSON
6. **Reset** → `clear_filters()` → ready for next dataset

---

## Analysis Method

Claude reads each screenshot with Vision and checks:
- Panel rendered (not empty, no error message)
- Data actually updated after filter/chart change
- No layout overflow or clipped elements
- Stat values plausible (not NaN/None displayed)
- Chart has axes, labels, data points visible

---

## Report Format

**Output:** `docs/qa/2026-02-23-qa-report.md`

```markdown
# DGS QA Report — 2026-02-23

## Summary
- Datasets tested: 10
- Scenarios run: N
- Issues found: X (Critical: A, Warning: B, Info: C)
- Bugs fixed: Y commits

## Per-Dataset Results
### 01_sales_simple.csv
- ✅ Load: ok
- ⚠️ filter_panel: stat_panel not updated after filter
- ...

## Issues & Fixes
| # | Panel | Symptom | Severity | Fix commit |
|---|-------|---------|----------|-----------|
```

---

## Bug Fix Policy

| Severity | Criteria | Action |
|----------|----------|--------|
| Critical | Crash, data loss, blank panel | Fix + commit immediately |
| Warning | Visual glitch, stale state | Fix + commit |
| Info | UX improvement, cosmetic | Report only |

---

## Files to Create

- `data_graph_studio/ui/controllers/ipc_controller.py` — add 5 new IPC handlers
- `tools/dgs_qa_runner.py` — test runner script
- `docs/qa/2026-02-23-qa-report.md` — generated during run
