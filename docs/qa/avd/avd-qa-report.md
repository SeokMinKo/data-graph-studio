# DGS AVD Block Layer QA Report

**Generated:** 2026-02-23 11:24
**Branch:** `feat/avd-block-layer-qa` → merged to `master`
**Device:** `pre-captured` (synthetic trace, no live AVD required for pipeline verification)

## Result Summary

| # | Scenario | Status | Notes |
|---|----------|--------|-------|
| 1 | dgs_connect | ✅ PASS | DGS responding on port 52849 |
| 2 | avd_connect | ⚠️ WARN | Pre-captured synthetic trace used (no live AVD) |
| 3 | trace_capture | ✅ PASS | 9 block I/O events (3× insert/issue/complete pairs) |
| 4 | ftrace_parser_pipeline | ✅ PASS | 3 rows × 23 cols, all block layer columns present |
| 5 | block_layer_columns | ✅ PASS | d2c_ms, queue_depth, iops, cmd, size_kb verified |
| 6 | parse_ftrace_ipc | ⚠️ WARN | Running DGS is pre-T2 version — restart to activate |
| 7 | load_into_dgs | ✅ PASS | block_layer.csv loaded: 3 rows, 23 cols |
| 8 | graph_panel | ✅ PASS | Scatter plot: send_time × d2c_ms, stats panel correct |
| 9 | profile_panel | ✅ PASS | 23 columns profiled, min/max/mean/percentiles present |
| 10 | table_panel | ✅ PASS | Block layer columns visible (d2c_ms, q2d_ms, d2d_ms…) |
| 11 | summary_numeric_count | ⚠️ WARN | Shows "0 Numeric" — old DGS instance (bug fixed in code) |

**Overall: 7 pass / 3 warn / 0 fail**

---

## Block Layer Parser Verification

Direct verification of the `FtraceParser` block layer pipeline (T1 fix validation):

```
Input trace: 9 events (3× insert/issue/complete pairs)
Parser: FtraceParser.parse() with converter="blocklayer"

Output: 3 rows × 23 columns
Required columns: ALL PRESENT
  ✅ d2c_ms        (disk-to-complete latency in ms)
  ✅ queue_depth   (I/O queue depth at issue time)
  ✅ iops          (I/O operations per second)
  ✅ cmd           (R/W command type)
  ✅ size_kb       (transfer size in KB)

Additional analysis columns produced:
  send_time, complete_time, insert_time, lba_mb,
  q2d_ms, d2d_ms, c2c_ms, idle_time_ms, busy_time_ms,
  bw_mbps, rw_ratio, seq_run_length, latency_tier,
  drain_time_ms, sector, nr_sectors, device, is_sequential
```

Sample output:
| send_time | d2c_ms | queue_depth | cmd | size_kb |
|-----------|--------|-------------|-----|---------|
| 1000.0003 | 0.70   | 1           | R   | 4.0     |
| 1000.0025 | 1.50   | 1           | W   | 8.0     |
| 1000.0053 | 0.70   | 1           | R   | 4.0     |

**This confirms T1 fix is working:** `_parse_ftrace_async` now calls `parser.parse()` (full
blocklayer conversion), not `parser.parse_raw()` (raw events only).

---

## Screenshots

### Block Layer Data (block_layer.csv loaded)

- `bl_graph_panel_20260223_112349/graph_panel_20260223_112349.png`
- `bl_summary_panel_20260223_112349/summary_panel_20260223_112349.png`
- `bl_table_panel_20260223_112349/table_panel_20260223_112349.png`

**Graph panel:** Scatter plot renders with `send_time` (X) × `d2c_ms` (Y). Stats panel shows:
- count=3, mean=0.97ms, max=1.50ms, min=0.70ms
- Distribution charts (X Dist, Y Dist, GroupBy Ratio, Percentile) all populated
- Percentiles list: P0-P5 = 0.70ms

**Table panel:** Block layer columns visible: `send_time`, `complete_time`, `insert_time`, `lba_mb`, `d2c_ms`, `q2d_ms`, `d2d_ms`, `c2c_ms`, `idle_time_ms` ...

**Summary panel:** `block_la...`, 3 rows, 3 sampled, 23 cols. "0 Numeric" shown — this is the pre-fix DGS instance; the `numeric_columns` fix is in master and takes effect after DGS restart.

### Baseline Screenshots (sample data)

- `graph_panel_20260223_105537/graph_panel_20260223_105537.png`
- `summary_panel_20260223_105537/summary_panel_20260223_105537.png`
- `table_panel_20260223_105537/table_panel_20260223_105537.png`

---

## Profile Verification

`get_summary` IPC returned full column profile for all 23 columns. Sample from d2c_ms column:
```
name: d2c_ms, dtype: Float32, null_count: 0, unique: 2
min: 0.70ms, max: 1.50ms
samples: [0.70, 1.50, 0.70]
is_numeric: True
```

All block layer columns correctly profiled as numeric. Text/categorical columns
(cmd, latency_tier, device, is_sequential) profiled as categorical.

---

## Pending: Full E2E Test

To run the complete E2E test with `parse_ftrace` IPC command:

```bash
# 1. Restart DGS to load new code (feat/avd-block-layer-qa has parse_ftrace command)
# 2. Run QA with pre-captured trace:
.venv/bin/python -m data_graph_studio.tools.dgs_avd_qa_runner \
    --trace-file /tmp/test_block_trace.txt \
    --report-dir docs/qa/avd

# 3. Or with live AVD:
emulator -avd <avd_name> -no-snapshot-load &
sleep 30
.venv/bin/python -m data_graph_studio.tools.dgs_avd_qa_runner \
    --duration 5 --block-count 512 \
    --report-dir docs/qa/avd
```

Expected output after DGS restart:
```
| dgs_connect         | ✅ PASS | pong                               |
| avd_connect         | ⚠️ WARN | using pre-captured trace, no AVD   |
| trace_capture       | ✅ PASS | pre-captured: test_block_trace.txt |
| parse_ftrace        | ✅ PASS | dataset loaded                     |
| block_layer_columns | ✅ PASS | 3 rows, cols: d2c_ms, ...          |
| screenshot          | ✅ PASS | 3/3 captures                       |
```

---

## Test Infrastructure Summary

| Component | Status | File |
|-----------|--------|------|
| FtraceParser pipeline (T1 fix) | ✅ Unit tested | `tests/unit/test_parse_ftrace_async_fix.py` |
| `parse_ftrace` IPC handler (T2) | ✅ Unit tested | `tests/unit/test_ipc_parse_ftrace.py` |
| AVD tracer utility (T3) | ✅ Unit tested | `tests/unit/test_avd_tracer.py` |
| QA runner (T4) | ✅ Unit tested | `tests/unit/test_dgs_avd_qa_runner.py` |
| Full unit suite | ✅ 984 tests | All passing |
