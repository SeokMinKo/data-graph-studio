# Plan: Converter Options UI + Re-computation on Change

## Critical Bug Found During Analysis

**`trace_controller.py:283-285`** calls `parser.parse_raw()` but never calls `parser.convert()`. Raw events (timestamp, cpu, task, pid, flags, event, details) are loaded into the dataset instead of converted data (d2c_ms, queue_depth, etc.). Graph presets silently fail because their required columns don't exist.

**Fix**: Worker emits both `raw_df` and `converted_df`. The converted df goes into the dataset; the raw df is preserved in `TraceContext` for re-conversion.

---

## Architecture Decision: Collapsible QDockWidget with PropertyPanelWidget

**Why not a dialog?** Converter options are "tweak and see" parameters — a modal dialog forces open→change→close→observe→reopen cycles. A dock lets users adjust and immediately see the graph update.

**Why PropertyPanelWidget?** It already has:
- `property_changed(group, item, value)` signal (property_panel.py:248)
- Type-aware editors: `QSpinBox` for INTEGER, `QDoubleSpinBox` for NUMBER, `QComboBox` for ENUM, `QLineEdit` for STRING (property_panel.py:306-358)
- Reset-to-defaults (property_panel.py:399-402)
- Tooltip support via `PropertyItem.description`

**Approach**: New `ConverterOptionsPanel` wraps `PropertyPanelWidget` inside a `QDockWidget`. Populated dynamically from converter option definitions. Debounced `options_changed(dict)` signal triggers re-conversion.

---

## Data Flow

```
Initial load (_parse_ftrace_async):
  parse_raw(file, settings) → raw_df           [worker thread]
  convert(raw_df, settings) → converted_df      [worker thread]
  emit((raw_df, converted_df))                  [to main thread]

  engine.load_dataset_from_dataframe(converted_df) → dataset_id
  TraceContext(raw_df, file_path, converter, settings, dataset_id) → stored
  _apply_graph_presets(converted_df, converter)

Re-conversion (on option change):
  TraceContext.raw_df + updated settings
  → FtraceParser.convert(raw_df, settings)      [main thread, fast]
  → engine.replace_dataset_df(dataset_id, new_df)
  → _on_data_loaded()                           [refreshes table+graph+summary]
```

---

## File-by-File Changes

### 1. `parsers/ftrace_parser.py` — Option definitions registry

Add after line 232 (before `_convert_blocklayer`). No behavior changes.

```python
# Converter option definitions — drives the UI
_CONVERTER_OPTION_DEFS: Dict[str, List[Dict[str, Any]]] = {
    "blocklayer": [
        {"name": "busy_queue_depth", "display": "Busy Queue Depth",
         "type": "int", "default": 32, "min": 1, "max": 1024,
         "tooltip": "Queue depth threshold to classify I/O as 'busy'"},
        {"name": "idle_queue_depth", "display": "Idle Queue Depth",
         "type": "int", "default": 4, "min": 0, "max": 256,
         "tooltip": "Queue depth threshold to classify I/O as 'idle'"},
        {"name": "window_sec", "display": "Window (sec)",
         "type": "float", "default": 1.0, "min": 0.01, "max": 60.0,
         "tooltip": "Sliding window size in seconds for time-based aggregation"},
        {"name": "latency_percentiles", "display": "Latency Percentiles",
         "type": "str", "default": "50,90,99",
         "tooltip": "Comma-separated percentile values to compute (e.g. 50,90,99)"},
        {"name": "drain_target_depth", "display": "Drain Target Depth",
         "type": "int", "default": 0, "min": 0, "max": 256,
         "tooltip": "Target queue depth for drain analysis"},
    ],
}

@classmethod
def get_converter_option_defs(cls, converter: str) -> List[Dict[str, Any]]:
    """Return option definitions for a converter (drives UI generation)."""
    return cls._CONVERTER_OPTION_DEFS.get(converter, [])
```

### 2. `ui/controllers/trace_controller.py` — Fix pipeline + TraceContext + reconvert

**a) Add TraceContext dataclass** (top of file, after imports):
```python
@dataclass
class TraceContext:
    """Preserves raw_df and settings for re-conversion."""
    raw_df: pl.DataFrame
    file_path: str
    converter: str
    settings: Dict[str, Any]
    dataset_id: str
```

**b) Init `_trace_context`** in `__init__`:
```python
def __init__(self, main_window):
    self.w = main_window
    self._trace_context: Optional[TraceContext] = None
```

**c) Fix worker in `_parse_ftrace_async`** (line 283-285):
```python
# BEFORE (bug — only raw events, no conversion):
def run(self_w):
    df = parser.parse_raw(file_path, settings)
    self_w.finished.emit(df)

# AFTER:
def run(self_w):
    raw_df = parser.parse_raw(file_path, settings)
    converted_df = parser.convert(raw_df, settings)
    self_w.finished.emit((raw_df, converted_df))
```

**d) Update `on_finished`** to unpack tuple and store context:
```python
def on_finished(result):
    raw_df, df = result
    # ... load df into dataset ...
    if dataset_id:
        self._trace_context = TraceContext(
            raw_df=raw_df, file_path=file_path,
            converter=converter, settings=dict(settings),
            dataset_id=dataset_id,
        )
```

**e) Add `reconvert()` method**:
```python
def reconvert(self, new_options: Dict[str, Any]) -> None:
    """Re-run converter with updated options and refresh UI."""
    ctx = self._trace_context
    if ctx is None:
        return
    ctx.settings["converter_options"] = new_options
    parser = FtraceParser()
    new_df = parser.convert(ctx.raw_df, ctx.settings)
    self.w.engine.replace_dataset_df(ctx.dataset_id, new_df)
    self.w._on_data_loaded()
```

### 3. `core/dataset_manager.py` — Add `replace_dataset_df()`

```python
def replace_dataset_df(self, dataset_id: str, df: pl.DataFrame) -> bool:
    """Replace the DataFrame of an existing dataset (for re-conversion).

    Args:
        dataset_id: Target dataset ID.
        df: New polars DataFrame.

    Returns:
        True on success, False if dataset not found.
    """
    ds = self._datasets.get(dataset_id)
    if ds is None:
        return False
    ds.df = df
    ds.lazy_df = df.lazy()
    logger.info("Dataset %s DataFrame replaced: %d rows", dataset_id, len(df))
    return True
```

### 4. `core/data_engine.py` — Facade method

```python
def replace_dataset_df(self, dataset_id: str, df: pl.DataFrame) -> bool:
    """Replace DataFrame for an existing dataset (re-conversion use case)."""
    return self._datasets_mgr.replace_dataset_df(dataset_id, df)
```

### 5. `ui/panels/converter_options_panel.py` — NEW FILE (~90 lines)

Wraps `PropertyPanelWidget`, builds from option defs, emits debounced `options_changed(dict)`.

```python
"""Converter Options Panel — editable parameters for ftrace converters."""
from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

from .property_panel import (
    PropertyPanel, PropertyPanelWidget, PropertyGroup, PropertyItem, PropertyType,
)

_TYPE_MAP = {"int": PropertyType.INTEGER, "float": PropertyType.NUMBER, "str": PropertyType.STRING}


class ConverterOptionsPanel(QWidget):
    """Editable converter options with debounced change signal."""

    options_changed = Signal(dict)  # {option_name: value, ...}

    DEBOUNCE_MS = 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._option_defs = []
        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.timeout.connect(self._emit_options)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._info_label = QLabel("No converter active")
        layout.addWidget(self._info_label)
        self._prop_widget = PropertyPanelWidget(self)
        self._prop_widget.property_changed.connect(self._on_property_changed)
        self._prop_widget.hide()
        layout.addWidget(self._prop_widget)

    def set_converter(self, converter: str, option_defs: list) -> None:
        """Populate panel from converter option definitions."""
        self._option_defs = option_defs
        if not option_defs:
            self._prop_widget.hide()
            self._info_label.setText("No options for this converter")
            self._info_label.show()
            return

        model = PropertyPanel()
        group = PropertyGroup(name="options", display_name=f"Converter: {converter}")
        for odef in option_defs:
            ptype = _TYPE_MAP.get(odef["type"], PropertyType.STRING)
            item = PropertyItem(
                name=odef["name"],
                display_name=odef["display"],
                property_type=ptype,
                value=odef["default"],
                default_value=odef["default"],
                description=odef.get("tooltip", ""),
                min_value=odef.get("min"),
                max_value=odef.get("max"),
            )
            group.items[odef["name"]] = item
        model.add_group(group)

        self._info_label.hide()
        self._prop_widget.set_model(model)
        self._prop_widget.show()

    def get_options(self) -> dict:
        """Return current option values as a dict."""
        result = {}
        for odef in self._option_defs:
            groups = self._prop_widget._model.groups
            if "options" in groups and odef["name"] in groups["options"].items:
                result[odef["name"]] = groups["options"].items[odef["name"]].value
            else:
                result[odef["name"]] = odef["default"]
        return result

    def clear(self) -> None:
        """Reset to empty state."""
        self._option_defs = []
        self._prop_widget.hide()
        self._info_label.setText("No converter active")
        self._info_label.show()

    def _on_property_changed(self, group, item, value):
        self._debounce.start(self.DEBOUNCE_MS)

    def _emit_options(self):
        self.options_changed.emit(self.get_options())
```

### 6. `ui/main_window.py` — Wire dock panel

**In `__init__`** (after other dock setup):
```python
self._converter_options_dock = None  # lazy creation
```

**Add method `_ensure_converter_options_dock()`**:
```python
def _ensure_converter_options_dock(self):
    if self._converter_options_dock is not None:
        return
    from .panels.converter_options_panel import ConverterOptionsPanel
    panel = ConverterOptionsPanel(self)
    dock = QDockWidget("Converter Options", self)
    dock.setWidget(panel)
    dock.setObjectName("ConverterOptionsDock")
    self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
    dock.hide()
    panel.options_changed.connect(self._trace_ctrl.reconvert)
    self._converter_options_dock = dock
    self._converter_options_panel = panel
```

**In TraceController's `on_finished`** (after successful load):
```python
# Show converter options panel
self.w._ensure_converter_options_dock()
from data_graph_studio.parsers import FtraceParser
defs = FtraceParser.get_converter_option_defs(converter)
self.w._converter_options_panel.set_converter(converter, defs)
self.w._converter_options_dock.show()
```

**In MenuSetupController** (View menu):
```
View → Converter Options  (toggle dock visibility)
```

---

## Signal/Slot Wiring

```
PropertyPanelWidget.property_changed(group, item, value)
  → ConverterOptionsPanel._on_property_changed()
      → QTimer debounce (300ms)
          → ConverterOptionsPanel._emit_options()
              → ConverterOptionsPanel.options_changed(dict)
                  → TraceController.reconvert(new_options)
                      → FtraceParser.convert(raw_df, updated_settings)
                      → DataEngine.replace_dataset_df(dataset_id, new_df)
                      → MainWindow._on_data_loaded()
                          → table_panel.set_data()
                          → graph_panel.refresh()
                          → summary_panel.refresh()
```

---

## Risk Assessment

| Risk | Severity | Mitigation |
|------|----------|------------|
| Raw DataFrame memory overhead | Low | Raw ftrace events are small text logs. ~10-50MB for millions of events. |
| Re-conversion blocks UI | Medium | Polars vectorized ops are fast. For huge traces, move to QThread later. Start synchronous — simpler. |
| Breaking existing tests | Low | Unit tests for FtraceParser test converter output, not the UI pipeline. The bug fix makes things correct. |
| Multiple trace datasets | Low | `_trace_context` tracks one active trace. Multi-trace = dict of contexts keyed by dataset_id (future). |
| PropertyPanelWidget integration | None | Already exists, well-tested, handles all needed types. |

---

## Implementation Order

1. **Add option defs registry** to `ftrace_parser.py` — pure data, no behavior change
2. **Add `replace_dataset_df`** to `dataset_manager.py` + `data_engine.py` — needed for re-conversion
3. **Fix the parse_raw bug** in `trace_controller.py` — critical correctness fix
4. **Add TraceContext + `reconvert()`** to `trace_controller.py` — raw_df preservation + re-conversion
5. **Create `ConverterOptionsPanel`** — new file, ~90 lines
6. **Wire into MainWindow** — dock, menu, signal connections
7. **Add tests** for option defs, replace_dataset_df, reconvert flow

## Files Summary

**New:**
- `data_graph_studio/ui/panels/converter_options_panel.py` (~90 lines)

**Modified:**
- `data_graph_studio/parsers/ftrace_parser.py` (+30 lines: option defs registry)
- `data_graph_studio/ui/controllers/trace_controller.py` (+55 lines: TraceContext, fix bug, reconvert)
- `data_graph_studio/core/dataset_manager.py` (+15 lines: replace_dataset_df)
- `data_graph_studio/core/data_engine.py` (+5 lines: facade method)
- `data_graph_studio/ui/main_window.py` (+20 lines: dock wiring)
- `data_graph_studio/ui/controllers/menu_setup_controller.py` (+5 lines: View menu toggle)
