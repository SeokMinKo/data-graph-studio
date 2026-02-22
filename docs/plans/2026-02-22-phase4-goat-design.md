# Phase 4: GOAT Code 9.0+ — Design Document

**Date:** 2026-02-22
**Goal:** Raise GOAT Code score from 7.55 → 9.0+
**Branch:** `goat-phase4`

---

## Problem

Architecture score (6.5/10) is dragging the average down. Qt imports exist in 6 core layer files, violating the layered architecture rule: "Domain must NEVER reference outer layers."

Current state:
- `state.py` — QObject + 27 Signals (1804 lines)
- `ipc_server.py` — QTcpServer/QTcpSocket (256 lines)
- `export_controller.py` — QPainter/QSvgGenerator/QThread (711 lines)
- `clipboard_manager.py` — QApplication/QImage/QMimeData (298 lines)
- `shortcut_controller.py` — QKeySequence (427 lines)
- `profile_store.py` — QtConcurrent.run (121 lines, optional import)

---

## Design

### Phase 4a: state.py → Observable

**Pattern:** Same as Phase 3 (marking, comparison_manager, etc.)

AppState removes `QObject` inheritance and `Signal` declarations. Emits string-keyed events via `Observable.emit()`. A new `AppStateAdapter(QObject)` in `ui/adapters/` bridges to Qt Signals for UI consumption.

**27 signals to migrate:**
```
data_loaded, data_cleared,
group_zone_changed, value_zone_changed, hover_zone_changed,
filter_changed, sort_changed,
selection_changed, limit_to_marking_changed,
chart_settings_changed, tool_mode_changed, grid_view_changed,
summary_updated,
profile_loaded, profile_cleared, profile_saved,
setting_activated, setting_added, setting_removed,
floating_window_opened, floating_window_closed,
dataset_added, dataset_removed, dataset_activated, dataset_updated,
comparison_mode_changed, comparison_settings_changed
```

All 38 UI files that call `state.signal.connect(...)` → updated to use `app_state_adapter.signal.connect(...)` or `state.subscribe("event", callback)`.

**Test:** `tests/unit/test_app_state_observable.py` — verify all 27 events fire correctly.

---

### Phase 4b: clipboard_manager.py → UI Layer

`ClipboardManager` inherently uses Qt clipboard/image APIs. It belongs in `ui/` not `core/`. Move the file to `data_graph_studio/ui/clipboard_manager.py`. Update all imports.

No interface needed — it's pure UI infrastructure.

---

### Phase 4c: shortcut_controller.py → Abstract QKeySequence

`ShortcutController` uses `QKeySequence` only for key string parsing. Options:
- Move to `ui/` (cleanest, it's UI behavior)
- Or abstract the parse step behind `IKeyParser` ABC

**Decision:** Move to `ui/controllers/` since keyboard shortcuts are a UI concern.

---

### Phase 4d: profile_store.py → threading.Thread

`profile_store.py` uses `QtConcurrent.run` for async profile loading (optional import with try/except). Replace with `concurrent.futures.ThreadPoolExecutor` — already available in stdlib, zero Qt dependency.

---

### Phase 4e: ipc_server.py → asyncio

`IpcServer` uses `QTcpServer`/`QTcpSocket` for inter-process communication. Replace with Python's `asyncio` TCP server. Maintains same API surface (start/stop, message callbacks).

---

### Phase 4f: export_controller.py → IImageRenderer interface

`ExportController` uses `QPainter`/`QSvgGenerator`/`QThread` for rendering. This is legitimately rendering infrastructure. Design:
- Keep `ExportController` in core but extract `IExportRenderer` ABC
- Move `QtExportRenderer` to `ui/renderers/`
- `ExportController.__init__` accepts `renderer: IExportRenderer` (DI)

This keeps core Qt-free while acknowledging rendering is rendering.

---

### Phase 4g: Large function decomposition

8 functions exceed 100 lines (GOAT limit: 50). Priority targets:
- `comparison_report.py:_generate_html_report` — 277 lines → split into section generators
- `expression_engine.py:_evaluate_function` — 217 lines → dispatch table per function type

---

### Phase 4h: Docstrings + observability

- Raise docstring coverage 76% → 85%+ on all public functions missing them
- Add explicit timeout parameters to IPC and network calls

---

## Expected Score After Phase 4

| Category | Before | After |
|---|---|---|
| Layered Architecture | 6.5 | 9.0 |
| Function Design | 7.2 | 8.5 |
| Domain Modeling | 8.0 | 8.5 |
| Error Strategy | 7.3 | 8.0 |
| Test Quality | 7.8 | 8.5 |
| Coding Conventions | 8.1 | 9.0 |
| Observability | 7.6 | 9.0 |
| Extensibility | 7.9 | 9.0 |
| **Average** | **7.55** | **8.6** |

---

## Implementation Tasks

1. **4a-T1:** Migrate state.py AppState → Observable (core change)
2. **4a-T2:** Create AppStateAdapter in ui/adapters/
3. **4a-T3:** Update 38 UI files to use AppStateAdapter
4. **4b-T1:** Move clipboard_manager.py to ui/
5. **4c-T1:** Move shortcut_controller.py to ui/controllers/
6. **4d-T1:** Replace QtConcurrent in profile_store.py with ThreadPoolExecutor
7. **4e-T1:** Replace QTcpServer in ipc_server.py with asyncio
8. **4f-T1:** Extract IExportRenderer interface + move QtExportRenderer to ui/
9. **4g-T1:** Split _generate_html_report (277 lines)
10. **4g-T2:** Split _evaluate_function (217 lines) with dispatch table
11. **4h-T1:** Add missing docstrings to reach 85%+
12. **4h-T2:** Add timeout params to IPC/network calls
