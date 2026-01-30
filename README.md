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
- **Rect Select** - Drag rectangle to select points
- **Lasso Select** - Draw freeform polygon to select points
- **Limit to Marking** - Filter table to show only selected rows
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

## 🖥️ Screenshot

```
┌─────────────────────────────────────────────────────────────┐
│  📊 SUMMARY    Rows: 1,000,000 │ Selected: 1,234           │
├─────────────────────────────────────────────────────────────┤
│ Options │         📈 MAIN GRAPH                  │ Stats   │
│ ────────│  🔍 ✋ ▢ 〰️ ✕ 🔄                        │ ────────│
│ Chart   │         [Interactive Chart]            │ X Dist  │
│ Axes    │              ●  ●                      │ Y Dist  │
│ Style   │           ●  ●  ●  ●                   │ Summary │
│ Legend  │        ●  ●  ●  ●  ●                   │         │
├─────────────────────────────────────────────────────────────┤
│ X Zone  │ Group │      📋 TABLE        │ Value │ Hover   │
│ ────────│ Zone  │ 🔗 Limit to Marking  │ Zone  │ Zone    │
│ [date]  │ region│  Col1 │ Col2 │ ...  │ sales │ [cols]  │
│         │       │  ...  │ ...  │      │ (SUM) │         │
└─────────────────────────────────────────────────────────────┘
```

## 🚀 Installation

```bash
# Clone repository
git clone https://github.com/seokmin-ko/data-graph-studio.git
cd data-graph-studio

# Create virtual environment
python -m venv venv
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Install dependencies
pip install -r requirements.txt

# Or install in dev mode
pip install -e ".[dev]"
```

## 📖 Usage

### Launch

```bash
# Run GUI
python main.py

# Open with file
python main.py data.csv
```

### Basic Workflow

1. **Load Data** - Drag & drop file or `File > Open`
   - Supported: CSV, TSV, Excel, Parquet, JSON

2. **Set X-Axis** - Drag column to X Zone (left)

3. **Set Y-Axis** - Drag numeric columns to Value Zone (right)
   - Select aggregation: SUM, AVG, MIN, MAX, COUNT, etc.
   - Add formula: `y*2`, `LOG(y)`, `y/1000`

4. **Group By** - Drag categorical columns to Group Zone
   - Creates multiple series with different colors

5. **Select Data** - Use Rect/Lasso select tools
   - Enable "Limit to Marking" to filter table

### Selection Tools

| Tool | Shortcut | Description |
|------|----------|-------------|
| 🔍 Zoom | Z | Zoom into region |
| ✋ Pan | H | Pan/move view |
| ▢ Rect Select | R | Rectangle selection |
| 〰️ Lasso Select | L | Freeform polygon selection |
| ✕ Clear | Escape | Clear selection |
| 🔄 Reset | Home | Reset view |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| Ctrl+O | Open file |
| Ctrl+S | Save project |
| Ctrl+F | Search |
| Ctrl+A | Select all |
| +/- | Zoom in/out |
| Escape | Clear selection |

## 🔧 Tech Stack

- **UI**: PySide6 (Qt 6)
- **Data Engine**: Polars (high-performance DataFrame)
- **Charts**: PyQtGraph (real-time) + OpenGL
- **File I/O**: Apache Arrow, OpenPyXL

## 📊 Performance

| Data Size | Load Time | Filter/Sort | Memory |
|-----------|-----------|-------------|--------|
| 100K rows | < 1s | < 0.3s | < 200MB |
| 1M rows | < 5s | < 1s | < 1GB |
| 10M rows | < 30s | < 3s | < 4GB |

## 📁 Project Structure

```
data-graph-studio/
├── main.py                    # Entry point
├── data_graph_studio/
│   ├── core/
│   │   ├── data_engine.py     # Polars data engine
│   │   ├── state.py           # App state management
│   │   ├── marking.py         # Selection/marking system
│   │   └── statistics.py      # Statistics calculations
│   ├── ui/
│   │   ├── main_window.py     # Main window
│   │   └── panels/
│   │       ├── graph_panel.py # Chart + options + stats
│   │       └── table_panel.py # Table + zones
│   ├── graph/
│   │   ├── sampling.py        # LTTB, Min-Max sampling
│   │   └── charts/            # Chart implementations
│   └── report/                # Export (PDF, PPTX, DOCX)
├── tests/
├── test_data/                 # Sample datasets
├── requirements.txt
└── PRD.md                     # Product requirements
```

## 🧪 Testing

```bash
# Run tests
pytest

# With coverage
pytest --cov=data_graph_studio
```

## 🗺️ Roadmap

- [x] Core data engine with Polars
- [x] Basic charts (Line, Bar, Scatter, Area)
- [x] Drag & drop zone system
- [x] Rect Select & Lasso Select
- [x] Limit to Marking (table filtering)
- [x] Selection statistics
- [x] Big data sampling (LTTB, Min-Max)
- [x] Multi-dataset comparison
- [ ] Report generation (PDF, PPTX)
- [ ] Dashboard layout saving
- [ ] Plugin system

## 📄 License

MIT License

## 🤝 Contributing

Issues and PRs welcome!

---

Made with ❤️ by Seokmin Ko
