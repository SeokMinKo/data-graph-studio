# Data Graph Studio — GOAT Code Architecture Audit Report

**Date:** 2026-02-22
**Branch:** goat-code-audit
**Codebase:** `/Users/lov2fn/Projects/data-graph-studio/`
**Total Python Files:** ~155
**Total Lines of Code:** ~73,151
**Overall Compliance Score: 4.8/10**

---

## Executive Summary

The project demonstrates semi-structured architecture that partially adheres to layered design principles but suffers from significant layer boundary violations, god objects, and inconsistent adherence to the GOAT Code standard. Domain modeling is strong (dataclasses, frozen entities), but observability is weak and function design needs improvement.

---

## Section Scores

| Criterion | Score | Status |
|---|---|---|
| Domain Modeling | 8/10 | 🟢 Good |
| Test Coverage | 7/10 | 🟢 Good |
| Error Strategy | 6/10 | 🟡 Partial |
| Layered Architecture | 5/10 | 🟡 Partial |
| Function Design | 4/10 | 🔴 Weak |
| Coding Conventions | 3/10 | 🔴 Weak |
| Configuration | 2/10 | 🔴 Critical |
| Observability | 2/10 | 🔴 Critical |

---

## 1. Layer Violation Findings — CRITICAL

### 10 Core Layer → Qt Dependencies

| File | Violation | Severity |
|---|---|---|
| `core/state.py` | `from PySide6.QtCore import QObject, Signal` | 🔴 CRITICAL |
| `core/streaming_controller.py` | `from PySide6.QtCore import QObject, Signal` | 🔴 CRITICAL |
| `core/filtering.py` | `from PySide6.QtCore import QObject, Signal` | 🔴 CRITICAL |
| `core/clipboard_manager.py` | `from PySide6.QtWidgets import QApplication` | 🔴 CRITICAL |
| `core/export_controller.py` | `from PySide6.QtGui import QImage, QPainter...` | 🔴 CRITICAL |
| `core/marking.py` | `from PySide6.QtCore import QObject, Signal` | 🔴 CRITICAL |
| `core/view_sync.py` | `from PySide6.QtCore import QObject, QTimer...` | 🔴 CRITICAL |
| `core/ipc_server.py` | `from PySide6.QtCore import QObject, Signal` | 🔴 CRITICAL |
| `core/profile_comparison_controller.py` | `from ..ui.panels.profile_overlay import ProfileOverlayRenderer` | 🔴 CRITICAL |
| `core/shortcut_controller.py` | `from ..ui.shortcuts import ShortcutManager...` | 🔴 CRITICAL |

**Impact:** Core layer cannot be tested independently or reused outside Qt application.

---

## 2. Function Design Issues

### Functions Exceeding 50 Lines

```
formula_parser.py::_eval_prepared()          117 lines
export_controller.py::_export_pdf()           89 lines
state.py::__init__()                          77 lines
clipboard_manager.py::_parse_html_table()     74 lines
file_watcher.py::watch()                      65 lines
expression_engine.py::_evaluate_ast()         64 lines
```

### Docstring Coverage: Only 23.9% (809/3390 functions)

### Magic Numbers & Hardcoded Constants

```python
DEFAULT_CHUNK_SIZE = 100_000        # not configurable
LARGE_FILE_THRESHOLD = 100 * 1024 * 1024
infer_schema_length=10000
seed=42
timeout=120                         # not injectable
```

---

## 3. Error Strategy

- **Exception-based:** 497 (70.7%) ✓
- **Fail-fast validation:** 74 (10.5%) — insufficient
- **Result[T,E]:** 0
- **ErrorCode enum:** 0

Custom exceptions found: `CycleDetectedError`, `ExpressionError`, `SecurityError`, `FormulaError`

**Issue:** Silent failures — `drop_column()` returns without error when column doesn't exist.

---

## 4. Domain Modeling — GOOD

### Strengths
- Frozen dataclasses with immutable update pattern (`dataclasses.replace`)
- Explicit enums: `ChartType` (30+ types), `ToolMode`, `SessionState`

### Gaps
- Some raw dicts still used for domain data

---

## 5. Coding Conventions — WEAK

### God Object Files (>500 lines)

| File | Lines | Max Nesting |
|---|---|---|
| `ui/panels/table_panel.py` | 2793 | 7 |
| `ui/panels/graph_panel.py` | 2489 | **13** |
| `ui/panels/main_graph.py` | 2158 | **15** |
| `ui/main_window.py` | 2023 | 8 |

### Logging
- Structured (logger): 27 files
- Unstructured (print): 13 files
- No logging: 115 files

---

## 6. Observability — CRITICAL

- No correlation IDs
- No request tracking
- No retry strategy or circuit breaker
- No performance metrics
- Timeouts: present but hardcoded and not injectable

---

## 7. Configuration — CRITICAL

No `config/` module exists. All settings are hardcoded.

**Expected (missing):**
```
config/
├── constants.py    # application-wide constants
├── defaults.py     # tunable defaults
└── loader.py       # load from env/files
```

---

## 8. Test Coverage — GOOD

- 86 test files, ~15,000 LOC (20% ratio)
- Good boundary value testing
- Gaps: no property-based tests (hypothesis), limited error path coverage

---

## Refactoring Roadmap

### 🔴 Phase 1 — Critical (8–12 weeks)

1. Extract Qt from Core — create adapter/signal layer
2. Eliminate God Objects — split graph_panel.py, table_panel.py
3. Add `config/` module — externalize magic numbers
4. Implement structured logging + correlation IDs

### 🟡 Phase 2 — Important (4–6 weeks)

5. Docstring coverage: 23.9% → 80%+
6. Reduce nesting: 13/15 levels → max 3
7. Fail Fast input validation at layer boundaries

### 🟢 Phase 3 — Nice to Have

8. Property-based tests (hypothesis)
9. Error path coverage audit
10. Dependency linting (no circular imports)

---

## Architecture Transformation Target

```
Current                           Target
───────────────────────────────   ───────────────────────────────
core/ imports Qt directly         core/ is framework-agnostic
Layer violations                  Clean layer separation
God objects (2793 lines)          Focused classes (< 300 lines)
Magic numbers everywhere          config/ module with overrides
Silent failures                   Explicit error handling
No tracing                        Correlation IDs + JSON logs
```
