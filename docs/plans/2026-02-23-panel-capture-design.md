# Panel Capture Feature — Design Doc

**Date:** 2026-02-23
**Purpose:** AI-driven UI/UX debugging — allow AI agents to capture DGS panel screenshots via CLI and IPC

---

## Summary

Add a CLI-accessible screenshot/capture system to DGS. Designed exclusively for AI agents (not end users) to verify that the app renders correctly after refactoring or feature changes.

---

## Architecture

```
CLI Tool (dgs_capture)
    │
    ├── [running DGS] → IPC socket → CAPTURE command → QWidget.grab()
    │                                                         ↓
    └── [headless]   → --capture-mode flag → QOffscreenSurface → QWidget.grab()
                                                                  ↓
                                                      PNG + state.json + summary.txt
```

---

## IPC Protocol

**Request:**
```json
{
  "command": "capture",
  "target": "all" | "window" | "<panel_name>",
  "output_dir": "/tmp/dgs_captures/",
  "format": "png"
}
```

**Response:**
```json
{
  "status": "ok",
  "captures": [
    {
      "name": "graph_panel",
      "file": "/tmp/dgs_captures/graph_panel_20260223_074500.png",
      "state": {
        "visible": true,
        "size": [800, 600],
        "data_loaded": true,
        "row_count": 1234,
        "active_filters": 2
      },
      "summary": "graph_panel: bar chart, 1234 rows, 2 filters active, no errors"
    }
  ]
}
```

**Supported panel targets:**
`window`, `graph_panel`, `table_panel`, `filter_panel`, `stat_panel`,
`details_panel`, `summary_panel`, `history_panel`, `dashboard_panel`,
`comparison_stats_panel`

---

## Files

### New files
| File | Purpose |
|---|---|
| `data_graph_studio/core/capture_protocol.py` | IPC capture command spec (ABC + value objects) |
| `data_graph_studio/ui/capture_service.py` | QWidget.grab() + offscreen rendering |
| `data_graph_studio/tools/dgs_capture.py` | CLI entry point |
| `tests/unit/test_capture_protocol.py` | Unit tests for value objects |
| `tests/integration/test_capture_ipc.py` | IPC roundtrip integration tests |

### Modified files
| File | Change |
|---|---|
| `data_graph_studio/core/ipc_server.py` | Add `capture` command handler (~30 lines) |
| `data_graph_studio/ui/main_window.py` | Add `--capture-mode` CLI flag (~20 lines) |

---

## GOAT Code Compliance

```python
# capture_protocol.py
@dataclass
class CaptureRequest:
    target: str        # "all" | "window" | panel_name
    output_dir: Path
    format: str = "png"

@dataclass
class CaptureResult:
    name: str
    file: Path
    state: Dict[str, Any]
    summary: str
    error: Optional[str] = None

class ICaptureService(ABC):
    @abstractmethod
    def capture(self, request: CaptureRequest) -> List[CaptureResult]: ...
```

- **Layered**: `capture_protocol.py` in core (no Qt), `capture_service.py` in ui (Qt)
- **ABC-based**: `ICaptureService` enables testing without Qt
- **Structured logging**: `logger.debug("capture.start", extra={"target": target})`
- **Metrics**: `get_metrics().increment("capture.completed")`
- **Tests**: unit (value objects) + integration (IPC roundtrip)

---

## CLI Usage

```bash
# Connect to running DGS
python -m dgs_capture --connect --target all --output-dir /tmp/captures

# Specific panel
python -m dgs_capture --connect --target graph_panel

# Headless (launch + capture + exit)
python -m dgs_capture --headless --target all --data sample.csv
```

---

## Approved: 2026-02-23
