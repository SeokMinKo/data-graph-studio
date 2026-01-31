"""Quick functionality test"""
import sys
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer

app = QApplication(sys.argv)

try:
    from data_graph_studio.ui.main_window import MainWindow
    win = MainWindow()
    
    # Load test data
    from data_graph_studio.core.data_engine import DataEngine
    engine = DataEngine()
    success = engine.load_file('test_data/01_sales_simple.csv')
    
    if success:
        print('[OK] Data loaded successfully')
        df = engine.df
        print(f'    Rows: {len(df)}, Columns: {len(df.columns)}')
        print(f'    Columns: {list(df.columns)}')
    else:
        print('[FAIL] Data loading failed')
    
    # Test state
    from data_graph_studio.core.state import AppState, ChartType
    state = AppState()
    state.set_chart_type(ChartType.SCATTER)
    print(f'[OK] State: set_chart_type called successfully')
    
    # Test theme
    from data_graph_studio.ui.theme import ThemeManager
    tm = ThemeManager()
    tm.set_theme('dark')
    print(f'[OK] Theme: {tm.current_theme.name}')
    
    # Test report
    from data_graph_studio.core.report import ReportMetadata, ReportData, ReportOptions
    from datetime import datetime
    meta = ReportMetadata(title='Test Report', created_at=datetime.now())
    print(f'[OK] Report: {meta.title}')
    
    # Test expressions
    from data_graph_studio.core.expression_engine import ExpressionEngine
    ee = ExpressionEngine()
    result = ee.evaluate('sales * 2', df)
    print(f'[OK] Expression: sales * 2 evaluated (first value: {result[0]})')
    
    print('\n=== All quick tests passed! ===')
    
except Exception as e:
    print(f'[FAIL] Error: {e}')
    import traceback
    traceback.print_exc()

app.quit()
