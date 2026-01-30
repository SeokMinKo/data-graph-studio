"""
Test script for new features
"""
import sys
import os

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

def test_imports():
    """Test all new imports work"""
    print("Testing imports...")
    
    # Core
    from data_graph_studio.core.state import AppState, FilterCondition
    from data_graph_studio.core.data_engine import DataEngine, FileType, DelimiterType
    print("  ✓ Core imports OK")
    
    # Dialogs
    from data_graph_studio.ui.dialogs import ParsingPreviewDialog, ParsingSettings
    print("  ✓ Dialogs imports OK")
    
    # Panels
    from data_graph_studio.ui.panels.table_panel import (
        TablePanel, XAxisZone, GroupZone, ValueZone, 
        FilterBar, HiddenColumnsBar, DataTableView
    )
    print("  ✓ TablePanel imports OK")
    
    from data_graph_studio.ui.panels.graph_panel import (
        GraphPanel, GraphOptionsPanel, LegendSettingsPanel, 
        StatPanel, MainGraph, ColorButton
    )
    print("  ✓ GraphPanel imports OK")
    
    from data_graph_studio.ui.panels.grouped_table_model import GroupedTableModel
    print("  ✓ GroupedTableModel imports OK")
    
    # Main window
    from data_graph_studio.ui.main_window import MainWindow, DataLoaderThread, DataLoaderThreadWithSettings
    print("  ✓ MainWindow imports OK")
    
    return True


def test_state_features():
    """Test state management features"""
    print("\nTesting state features...")
    
    from data_graph_studio.core.state import AppState
    
    state = AppState()
    
    # Test X column
    state.set_x_column("Time")
    assert state.x_column == "Time", "X column not set"
    print("  ✓ X column set/get works")
    
    # Test filters
    state.add_filter("Device", "eq", "SSD_A")
    assert len(state.filters) == 1, "Filter not added"
    assert state.filters[0].column == "Device"
    print("  ✓ Filter add works")
    
    state.add_filter("IOPS", "gt", 1000)
    assert len(state.filters) == 2
    print("  ✓ Multiple filters work")
    
    state.remove_filter(0)
    assert len(state.filters) == 1
    print("  ✓ Filter remove works")
    
    state.clear_filters()
    assert len(state.filters) == 0
    print("  ✓ Filter clear works")
    
    # Test hidden columns
    state.set_column_order(["A", "B", "C", "D"])
    state.toggle_column_visibility("B")
    visible = state.get_visible_columns()
    assert "B" not in visible, "Column not hidden"
    assert "A" in visible
    print("  ✓ Column visibility works")
    
    return True


def test_data_engine():
    """Test data engine loading"""
    print("\nTesting data engine...")
    
    from data_graph_studio.core.data_engine import DataEngine, DelimiterType
    
    engine = DataEngine()
    
    # Test file loading
    test_file = os.path.join(os.path.dirname(__file__), "test_data.csv")
    if os.path.exists(test_file):
        success = engine.load_file(
            test_file,
            delimiter=",",
            delimiter_type=DelimiterType.COMMA,
            has_header=True
        )
        
        assert success, "File load failed"
        assert engine.is_loaded, "Engine not marked as loaded"
        assert engine.row_count == 12, f"Expected 12 rows, got {engine.row_count}"
        assert "Device" in engine.columns
        print(f"  ✓ CSV load works ({engine.row_count} rows, {engine.column_count} columns)")
        
        # Test filtering
        filtered = engine.filter("Device", "eq", "SSD_A")
        assert len(filtered) == 4, f"Filter failed, expected 4 got {len(filtered)}"
        print("  ✓ Data filtering works")
        
        # Test statistics
        stats = engine.get_statistics("Read_IOPS")
        assert "mean" in stats
        assert "min" in stats
        print(f"  ✓ Statistics works (Read_IOPS mean: {stats['mean']:.1f})")
    else:
        print("  ⚠ Test file not found, skipping load test")
    
    return True


def test_parsing_settings():
    """Test parsing settings dataclass"""
    print("\nTesting parsing settings...")
    
    from data_graph_studio.ui.dialogs.parsing_preview_dialog import ParsingSettings
    from data_graph_studio.core.data_engine import FileType, DelimiterType
    
    settings = ParsingSettings(
        file_path="test.csv",
        file_type=FileType.CSV,
        encoding="utf-8",
        delimiter=",",
        delimiter_type=DelimiterType.COMMA,
        has_header=True,
        skip_rows=0
    )
    
    assert settings.file_path == "test.csv"
    assert settings.file_type == FileType.CSV
    assert settings.has_header == True
    print("  ✓ ParsingSettings dataclass works")
    
    return True


def test_grouped_model():
    """Test grouped table model"""
    print("\nTesting grouped table model...")
    
    from data_graph_studio.ui.panels.grouped_table_model import GroupedTableModel
    import polars as pl
    
    model = GroupedTableModel()
    
    # Test with sample data
    df = pl.DataFrame({
        "Device": ["SSD_A", "SSD_A", "SSD_B", "SSD_B"],
        "IOPS": [1000, 1200, 800, 900],
        "Latency": [0.5, 0.6, 0.8, 0.7]
    })
    
    model.set_data(
        df,
        group_columns=["Device"],
        value_columns=["IOPS"],
        aggregations={"IOPS": "sum"}
    )
    
    assert model.rowCount() > 0, "Model has no rows"
    print(f"  ✓ Grouped model works ({model.rowCount()} visible rows)")
    
    # Test get_column_name
    col_name = model.get_column_name(1)
    assert col_name == "Device", f"Expected 'Device', got '{col_name}'"
    print("  ✓ get_column_name works")
    
    return True


def test_qt_widgets():
    """Test Qt widget creation (headless)"""
    print("\nTesting Qt widget creation...")
    
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt
    
    # Create app if not exists
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    
    from data_graph_studio.core.state import AppState
    from data_graph_studio.core.data_engine import DataEngine
    
    state = AppState()
    engine = DataEngine()
    
    # Test XAxisZone
    from data_graph_studio.ui.panels.table_panel import XAxisZone
    x_zone = XAxisZone(state)
    assert x_zone is not None
    print("  ✓ XAxisZone created")
    
    # Test FilterBar
    from data_graph_studio.ui.panels.table_panel import FilterBar
    filter_bar = FilterBar(state)
    assert filter_bar is not None
    print("  ✓ FilterBar created")
    
    # Test HiddenColumnsBar
    from data_graph_studio.ui.panels.table_panel import HiddenColumnsBar
    hidden_bar = HiddenColumnsBar(state)
    assert hidden_bar is not None
    print("  ✓ HiddenColumnsBar created")
    
    # Test LegendSettingsPanel
    from data_graph_studio.ui.panels.graph_panel import LegendSettingsPanel
    legend_panel = LegendSettingsPanel(state)
    legend_panel.set_series(["Series1", "Series2"])
    settings = legend_panel.get_legend_settings()
    assert "show" in settings
    assert len(settings["series"]) == 2
    print("  ✓ LegendSettingsPanel works")
    
    # Test ColorButton
    from data_graph_studio.ui.panels.graph_panel import ColorButton
    from PySide6.QtGui import QColor
    color_btn = ColorButton(QColor("#FF0000"))
    assert color_btn.color().name() == "#ff0000"
    print("  ✓ ColorButton works")
    
    # Test GraphOptionsPanel
    from data_graph_studio.ui.panels.graph_panel import GraphOptionsPanel
    options_panel = GraphOptionsPanel(state)
    opts = options_panel.get_chart_options()
    assert "line_width" in opts
    assert "grid_x" in opts
    print("  ✓ GraphOptionsPanel works")
    
    return True


def main():
    print("=" * 60)
    print("Data Graph Studio - New Features Test")
    print("=" * 60)
    
    all_passed = True
    
    try:
        all_passed &= test_imports()
        all_passed &= test_state_features()
        all_passed &= test_data_engine()
        all_passed &= test_parsing_settings()
        all_passed &= test_grouped_model()
        all_passed &= test_qt_widgets()
        
        print("\n" + "=" * 60)
        if all_passed:
            print("✅ ALL TESTS PASSED!")
        else:
            print("❌ SOME TESTS FAILED")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n❌ TEST ERROR: {e}")
        import traceback
        traceback.print_exc()
        all_passed = False
    
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
