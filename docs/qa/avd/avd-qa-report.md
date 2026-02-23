# DGS AVD Block Layer QA Report

**Generated:** 2026-02-23 11:38:36  
**Device:** `pre-captured`  
**Result:** 5 pass / 1 warn / 0 fail / 6 total

---

| Scenario | Status | Notes |
|----------|--------|-------|
| dgs_connect | ✅ PASS | pong |
| avd_connect | ⚠️ WARN | using pre-captured trace, no AVD |
| trace_capture | ✅ PASS | pre-captured: test_block_trace.txt |
| parse_ftrace | ✅ PASS | dataset loaded |
| block_layer_columns | ✅ PASS | 3 rows, cols: d2c_ms, queue_depth, iops, cmd, size_kb |
| screenshot | ✅ PASS | 3/3 captures |
