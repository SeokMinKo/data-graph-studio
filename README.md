# Data Graph Studio 📊

> Spotfire-like data visualization tool for big data (10M+ rows)

## ✨ Key Features

### 🚀 Big Data Performance
- Handle **10M+ rows** smoothly with intelligent sampling
- LTTB, Min-Max, and Random sampling algorithms
- OpenGL acceleration for large datasets
- Memory-optimized Polars DataFrame engine

### 📊 Interactive Visualization
- **Drag & Drop** columns to X-axis, Group, and Value zones
- Multiple chart types: Line, Bar, Scatter, Area, Box, Violin, Heatmap
- Real-time **bidirectional sync** between Graph ↔ Table
- Custom axis formatting (Excel-style: `#,##0`, `0.0%`, `"K"`, etc.)

### 🎯 Selection & Filtering
- **Rect Select** — drag rectangle to select points
- **Lasso Select** — draw freeform polygon to select points
- **Limit to Marking** — filter table to show only selected rows
- Selection statistics update in real-time (Mean, Median, Std, Min, Max)

### 📈 Statistics Panel
- X/Y Distribution histograms (adjustable bins)
- Summary statistics for all data or selection only
- Double-click histograms to expand

### 🔧 Advanced Features
- Y-axis formula transformation (`y*2`, `LOG(y)`, `SQRT(y)`)
- Hover data customization
- Profile save/load system
- Multi-dataset comparison (Overlay, Side-by-Side)
- Dashboard mode with multi-cell layouts
- Real-time streaming (file-watch)
- Computed columns (expression engine)
- Annotation system
- Dark / Light / Midnight themes
- Customizable keyboard shortcuts

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                     MainWindow (UI)                      │
│  ┌─────────┐ ┌───────────┐ ┌───────────┐ ┌───────────┐  │
│  │  Graph   │ │  Table    │ │  Summary  │ │ Dashboard │  │
│  │  Panel   │ │  Panel    │ │  Panel    │ │  Panel    │  │
│  └────┬─────┘ └─────┬─────┘ └─────┬─────┘ └─────┬─────┘  │
│       └──────────────┼─────────────┼─────────────┘        │
│                      ▼                                    │
│              DataEngine (Facade)                         │
│  ┌────────────┬────────────┬────────────┬──────────────┐ │
│  │ FileLoader │ DataQuery  │ DataExporter│DatasetManager│ │
│  │ (I/O)      │ (stateless)│ (stateless) │ (CRUD)      │ │
│  └────────────┴────────────┴────────────┴──────┬───────┘ │
│                                                 │        │
│                                       ComparisonEngine   │
│                                       (stats, diff)      │
└──────────────────────────────────────────────────────────┘
```

### Module Responsibilities

| Module | Description |
|--------|-------------|
| **FileLoader** | File type detection, CSV/Excel/Parquet/JSON loading, encoding normalisation, progress callbacks, lazy loading |
| **DataQuery** | Filter, sort, group-aggregate, statistics, profiling — stateless, receives `pl.DataFrame` as argument |
| **DataExporter** | Export to CSV, Excel, Parquet — stateless |
| **DatasetManager** | Multi-dataset CRUD, memory management, metadata |
| **ComparisonEngine** | Comparison statistics, merge, statistical tests, correlation analysis |
| **DataEngine** | Facade — delegates to the 5 modules above; 100 % backward-compatible API |

## 🚀 Installation

```bash
git clone https://github.com/seokmin-ko/data-graph-studio.git
cd data-graph-studio

python -m venv .venv
source .venv/bin/activate   # Linux/Mac
# .venv\Scripts\activate    # Windows

pip install -r requirements.txt
```

## 📖 Usage

### Launch

```bash
python main.py              # GUI
python main.py data.csv     # open file directly
```

### IPC Control (CLI)

```bash
python dgs_client.py ping
python dgs_client.py state
python dgs_client.py load path/to/file.csv
python dgs_client.py chart LINE
```

The IPC server auto-selects a free port (default 52849) and writes
`~/.dgs/ipc_port` so that `dgs_client.py` discovers it automatically.

### v2 Features

| Feature | Access |
|---------|--------|
| Dashboard mode | View → Dashboard Mode (or toolbar toggle) |
| Streaming | Toolbar ▶/⏸/⏹ buttons |
| Computed columns | Data → Add Calculated Field |
| Annotations | View → Annotation Panel; right-click graph |
| Themes | View → Theme → Dark / Light / Midnight |
| Keyboard shortcuts | Help → Keyboard Shortcuts; customisable via Settings |
| Export | File → Export → Image / Data / Report |

### Selection Tools

| Tool | Shortcut | Description |
|------|----------|-------------|
| 🔍 Zoom | Z | Zoom into region |
| ✋ Pan | H | Pan/move view |
| ▢ Rect Select | R | Rectangle selection |
| 〰️ Lasso Select | L | Freeform polygon selection |
| ✕ Clear | Escape | Clear selection |
| 🔄 Reset | Home | Reset view |

## 🔧 Tech Stack

- **UI**: PySide6 (Qt 6)
- **Data Engine**: Polars (high-performance DataFrame)
- **Charts**: PyQtGraph (real-time) + OpenGL
- **File I/O**: Apache Arrow, OpenPyXL

## 📁 Project Structure

```
data-graph-studio/
├── main.py                        # Entry point
├── dgs_client.py                  # IPC CLI client
├── data_graph_studio/
│   ├── core/
│   │   ├── data_engine.py         # DataEngine Facade
│   │   ├── file_loader.py         # FileLoader
│   │   ├── data_query.py          # DataQuery (stateless)
│   │   ├── data_exporter.py       # DataExporter (stateless)
│   │   ├── dataset_manager.py     # DatasetManager
│   │   ├── comparison_engine.py   # ComparisonEngine
│   │   ├── ipc_server.py          # IPC server + dynamic port
│   │   ├── state.py               # App state management
│   │   ├── marking.py             # Selection/marking
│   │   └── statistics.py          # Statistics calculations
│   ├── ui/
│   │   ├── main_window.py         # Main window
│   │   ├── controllers/           # Extracted controllers
│   │   └── panels/                # Graph, Table, Summary, Dashboard
│   ├── graph/
│   │   ├── sampling.py            # LTTB, Min-Max sampling
│   │   └── charts/                # Chart implementations
│   └── report/                    # Export (HTML, PPTX)
├── tests/                         # Pytest test suite
├── test_data/                     # Sample datasets
└── requirements.txt
```

## 🧪 Testing

```bash
pytest
pytest --cov=data_graph_studio
```

## 📄 License

MIT License

## 🤝 Contributing

Issues and PRs welcome!

---

Made with ❤️ by Seokmin Ko
