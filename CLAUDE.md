# CLAUDE.md - AI Assistant Guide for Data Graph Studio

## Project Overview

**Data Graph Studio** is a big data visualization tool designed to handle 10 million+ rows with a drag-and-drop interface. It combines Excel's Pivot Table functionality with Tableau's visualization capabilities while maintaining big data performance.

- **Version**: 0.1.0 (Alpha)
- **Python**: 3.9+
- **License**: MIT
- **Primary Language**: Python with Korean documentation/comments

## Quick Start Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e ".[dev]"

# Run the GUI application
python main.py
python main.py data.csv  # With a file

# Run tests
pytest
pytest --cov=data_graph_studio  # With coverage
pytest tests/test_data_engine.py -v  # Specific test file

# Code formatting
black data_graph_studio/
ruff check data_graph_studio/

# CLI usage
dgs info data.csv
dgs stats data.csv --output json
dgs gui
```

## Project Structure

```
data-graph-studio/
├── main.py                    # GUI entry point
├── setup.py                   # Package configuration
├── requirements.txt           # Dependencies
├── PRD.md                     # Product requirements (Korean)
├── README.md                  # User documentation (Korean)
│
├── data_graph_studio/         # Main package
│   ├── __init__.py           # Package init (version: 0.1.0)
│   ├── __main__.py           # Module entry point
│   ├── cli.py                # Click-based CLI
│   │
│   ├── core/                 # Core data processing
│   │   ├── data_engine.py    # Polars-based data engine
│   │   ├── state.py          # Application state (AppState)
│   │   ├── cache.py          # Multi-level caching (L1/L2/L3)
│   │   ├── expression_engine.py  # Calculated fields parser
│   │   └── project.py        # Project save/load (.dgs format)
│   │
│   ├── ui/                   # PySide6 UI layer
│   │   ├── main_window.py    # Main application window
│   │   ├── theme.py          # Light/Dark theme system
│   │   ├── shortcuts.py      # Keyboard shortcuts
│   │   ├── dashboard.py      # Dashboard layout
│   │   ├── panels/           # UI panels
│   │   │   ├── summary_panel.py      # Statistics display
│   │   │   ├── graph_panel.py        # PyQtGraph charts
│   │   │   ├── table_panel.py        # Data table with zones
│   │   │   └── grouped_table_model.py # Grouped data model
│   │   └── dialogs/
│   │       └── parsing_preview_dialog.py  # File parsing preview
│   │
│   ├── graph/                # Visualization
│   │   ├── sampling.py       # LTTB data sampling
│   │   └── charts/           # Advanced chart types
│   │       ├── box_plot.py
│   │       ├── violin_plot.py
│   │       ├── heatmap.py
│   │       ├── candlestick.py
│   │       └── waterfall.py
│   │
│   └── utils/
│       └── memory.py         # Memory monitoring (psutil)
│
├── tests/                    # Test suite (pytest + pytest-qt)
│   ├── test_data_engine.py
│   ├── test_state.py
│   ├── test_cache.py
│   ├── test_file_formats.py
│   ├── test_calculated_fields.py
│   ├── test_sampling.py
│   ├── test_advanced_charts.py
│   ├── test_grouped_table.py
│   ├── test_table_model.py
│   ├── test_dashboard.py
│   ├── test_multi_axis.py
│   ├── test_project.py
│   ├── test_integration.py
│   ├── test_shortcuts.py
│   └── test_theme.py
│
├── logs/                     # Application logs
└── test_data/                # Test data files
```

## Key Technologies

| Component | Technology | Purpose |
|-----------|-----------|---------|
| UI Framework | PySide6 (Qt 6) | Native GUI with High DPI support |
| Data Engine | Polars | High-performance DataFrame with lazy evaluation |
| Charts | PyQtGraph | Real-time interactive charts |
| Export | Plotly | Interactive HTML export |
| File I/O | Apache Arrow, OpenPyXL | Parquet, Excel support |
| CLI | Click | Command-line interface |
| Testing | pytest, pytest-qt | Unit and Qt widget testing |
| Formatting | black, ruff | Code style and linting |

## Architecture Patterns

### MVC Pattern
- **Model**: `core/state.py` (AppState), `core/data_engine.py` (DataEngine)
- **View**: `ui/panels/` (SummaryPanel, GraphPanel, TablePanel)
- **Controller**: `ui/main_window.py` (MainWindow coordinates everything)

### Key Classes

**DataEngine** (`core/data_engine.py`):
- Central data processing with Polars
- Chunk-based loading (100K rows default)
- Memory optimization via type downcasting
- Supports: CSV, Excel, Parquet, JSON, TSV

**AppState** (`core/state.py`):
- Chart settings, filter/sort conditions
- Group/Value column management
- Enums: `ChartType`, `AggregationType`, `ToolMode`

**MainWindow** (`ui/main_window.py`):
- 3-panel layout: Summary (10%), Graph (45%), Table (45%)
- Async data loading with progress dialog
- Menu bar, toolbar, status bar

### Signal/Slot Pattern (Qt)
```python
# Signals are defined in classes
progress_updated = Signal(float, str)  # progress, message
data_loaded = Signal(object)           # DataFrame

# Connect signals to slots
self.engine.progress_updated.connect(self.on_progress)
```

## Code Conventions

### Naming
- **Classes**: PascalCase (`MainWindow`, `DataEngine`, `AppState`)
- **Functions/Methods**: snake_case (`load_file`, `get_statistics`)
- **Constants**: SCREAMING_SNAKE_CASE (`DEFAULT_CHUNK_SIZE`, `LARGE_FILE_THRESHOLD`)
- **Modules**: lowercase with underscores (`data_engine.py`)

### Type Hints
All code uses type hints:
```python
def load_file(self, path: str, settings: Optional[ParsingSettings] = None) -> pl.DataFrame:
    ...
```

### Dataclasses for Configuration
```python
@dataclass
class ParsingSettings:
    delimiter: str = ","
    encoding: str = "utf-8"
    has_header: bool = True
    skip_rows: int = 0
```

### Enums for Fixed Options
```python
class ChartType(Enum):
    LINE = "line"
    BAR = "bar"
    SCATTER = "scatter"
    # ...
```

## Important Implementation Details

### Big Data Performance
- **Chunk loading**: Files loaded in 100K row chunks
- **LTTB sampling**: Max 10,000 points for visualization
- **Lazy evaluation**: Polars LazyFrame for large datasets
- **Virtual scrolling**: Table uses Qt's virtual scroll
- **Cache layers**: L1 (views), L2 (column stats), L3 (sort indices)

### File Format Support
```python
# Reading
engine.load_file("data.csv")      # CSV
engine.load_file("data.xlsx")     # Excel
engine.load_file("data.parquet")  # Parquet
engine.load_file("data.json")     # JSON

# Delimiter options
settings = ParsingSettings(delimiter="\t")  # TSV
settings = ParsingSettings(delimiter=";")   # Semicolon-separated
```

### Chart Types
- Basic: LINE, BAR, SCATTER, AREA, PIE
- Statistical: HISTOGRAM, BOX, VIOLIN
- Advanced: HEATMAP, CANDLESTICK, WATERFALL

### Aggregation Functions
`SUM`, `MEAN`, `MEDIAN`, `MIN`, `MAX`, `COUNT`, `STD`, `VAR`, `FIRST`, `LAST`

### Tool Modes (Graph Panel)
- `ZOOM`: Area zoom (shortcut: Z)
- `PAN`: Move view (shortcut: H)
- `RECT_SELECT`: Rectangle selection (shortcut: R)
- `LASSO_SELECT`: Free-form selection (shortcut: L)

## Testing Guidelines

### Running Tests
```bash
# All tests
pytest

# Specific module
pytest tests/test_data_engine.py -v

# With coverage
pytest --cov=data_graph_studio

# Qt tests require display (use xvfb on CI)
xvfb-run pytest tests/test_main_window.py
```

### Test Structure
```python
import pytest
from data_graph_studio.core.data_engine import DataEngine

class TestDataEngine:
    @pytest.fixture
    def engine(self):
        return DataEngine()

    def test_load_csv(self, engine, tmp_path):
        # Create test file
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("a,b\n1,2\n3,4")

        # Test loading
        df = engine.load_file(str(csv_file))
        assert len(df) == 2
```

### Qt Widget Tests
```python
import pytest
from pytestqt.qtbot import QtBot
from data_graph_studio.ui.main_window import MainWindow

def test_main_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    assert window.isVisible()
```

## Common Tasks

### Adding a New Chart Type
1. Create chart class in `data_graph_studio/graph/charts/`
2. Register in `charts/__init__.py`
3. Add to `ChartType` enum in `core/state.py`
4. Update `graph_panel.py` to handle the new type
5. Add tests in `tests/test_advanced_charts.py`

### Adding a New Aggregation
1. Add to `AggregationType` enum in `core/state.py`
2. Update `data_engine.py` aggregation logic
3. Update UI dropdowns in `table_panel.py`

### Adding a New File Format
1. Update `FileType` enum in `core/data_engine.py`
2. Add loading logic in `DataEngine.load_file()`
3. Update `parsing_preview_dialog.py` if needed
4. Add tests in `tests/test_file_formats.py`

### Modifying the UI Layout
1. Panels are in `ui/panels/`
2. Main layout is in `ui/main_window.py`
3. Use Qt's QSplitter for resizable sections
4. Theme colors are in `ui/theme.py`

## CLI Commands

```bash
# File info
dgs info data.csv
dgs info data.csv --output json

# Statistics
dgs stats data.csv
dgs stats data.csv --columns name,age --output csv

# Filter and export
dgs filter data.csv --condition "age > 30" --output filtered.csv

# Convert formats
dgs export data.csv --format parquet --output data.parquet

# SQL queries
dgs query data.csv --sql "SELECT name, AVG(age) FROM df GROUP BY name"

# Headless chart generation
dgs graph data.csv --x date --y sales --type line --output chart.png

# Start HTTP API server
dgs serve --port 8080
```

## Performance Targets

| Data Size | Load Time | Filter/Sort | Memory |
|-----------|-----------|-------------|--------|
| 100K rows | < 1s | < 0.3s | < 200MB |
| 1M rows | < 5s | < 1s | < 1GB |
| 10M rows | < 30s | < 3s | < 4GB |

## Common Pitfalls

1. **Memory with Large Files**: Always use chunk loading for files > 1M rows
2. **Qt Thread Safety**: UI updates must be on main thread; use signals for worker threads
3. **Polars vs Pandas**: This project uses Polars, not Pandas. Don't mix them.
4. **Type Downcasting**: Automatic type optimization may change data types
5. **Korean Text**: Some comments and docs are in Korean; code is in English

## File Locations Reference

- **Entry point**: `main.py`
- **Package version**: `data_graph_studio/__init__.py`
- **App state management**: `data_graph_studio/core/state.py`
- **Data processing**: `data_graph_studio/core/data_engine.py`
- **Main window**: `data_graph_studio/ui/main_window.py`
- **Theme/styling**: `data_graph_studio/ui/theme.py`
- **Chart rendering**: `data_graph_studio/ui/panels/graph_panel.py`
- **Table with zones**: `data_graph_studio/ui/panels/table_panel.py`
- **CLI commands**: `data_graph_studio/cli.py`

## Development Workflow

1. **Create feature branch** from main
2. **Write tests first** (TDD encouraged)
3. **Implement feature** following existing patterns
4. **Format code**: `black data_graph_studio/ && ruff check data_graph_studio/`
5. **Run tests**: `pytest`
6. **Commit with clear message** describing the change
7. **Create PR** with description of changes

## Notes for AI Assistants

- The codebase uses **Polars** for data processing, not Pandas
- UI is built with **PySide6** (Qt 6), not PyQt5 or tkinter
- Comments may be in **Korean**; code identifiers are in **English**
- The package was recently renamed from `src/` to `data_graph_studio/`
- Focus on **performance** - this tool targets 10M+ row datasets
- Use **type hints** consistently
- Follow the **MVC pattern** already established
- Maintain **backwards compatibility** with existing .dgs project files
