#!/usr/bin/env python3
"""
간단한 테스트 앱 - 문제 원인 파악용
"""

import sys
import traceback

def main():
    # Force unbuffered output
    sys.stdout.reconfigure(line_buffering=True)
    
    print("Step 1: Importing PySide6...", flush=True)
    try:
        from PySide6.QtWidgets import (
            QApplication, QMainWindow, QWidget, QVBoxLayout, 
            QLabel, QPushButton, QSplitter, QTextEdit
        )
        from PySide6.QtCore import Qt
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        return 1
    
    print("Step 2: Importing pyqtgraph...", flush=True)
    try:
        import pyqtgraph as pg
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        return 1
    
    print("Step 3: Importing polars...", flush=True)
    try:
        import polars as pl
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        return 1
    
    print("Step 4: Creating QApplication...", flush=True)
    try:
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        return 1
    
    print("Step 5: Creating simple window...", flush=True)
    try:
        class SimpleWindow(QMainWindow):
            def __init__(self):
                super().__init__()
                self.setWindowTitle("Data Graph Studio - TEST")
                self.setMinimumSize(800, 600)
                
                central = QWidget()
                self.setCentralWidget(central)
                layout = QVBoxLayout(central)
                
                # Label
                label = QLabel("✅ Data Graph Studio - Test Window Working!")
                label.setStyleSheet("font-size: 24px; font-weight: bold; color: green; padding: 20px;")
                layout.addWidget(label)
                
                # Splitter with pyqtgraph
                splitter = QSplitter(Qt.Vertical)
                
                # PyQtGraph widget
                self.plot_widget = pg.PlotWidget()
                self.plot_widget.setBackground('w')
                self.plot_widget.showGrid(x=True, y=True)
                
                # Plot some test data
                import numpy as np
                x = np.linspace(0, 10, 100)
                y = np.sin(x)
                self.plot_widget.plot(x, y, pen=pg.mkPen('b', width=2), name='sin(x)')
                
                splitter.addWidget(self.plot_widget)
                
                # Text area
                text = QTextEdit()
                text.setPlainText("If you see this window and a graph, the basic setup works!\n\n"
                                  "This is a test window to verify PyQtGraph is working correctly.")
                text.setStyleSheet("font-size: 14px; padding: 10px;")
                splitter.addWidget(text)
                
                layout.addWidget(splitter)
                
                # Button
                btn = QPushButton("Click to Close")
                btn.setStyleSheet("font-size: 16px; padding: 10px; background-color: #4CAF50; color: white;")
                btn.clicked.connect(self.close)
                layout.addWidget(btn)
        
        window = SimpleWindow()
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        traceback.print_exc()
        return 1
    
    print("Step 6: Positioning window at center...", flush=True)
    try:
        # 화면 중앙에 배치
        screen = app.primaryScreen().geometry()
        window.move(
            (screen.width() - window.width()) // 2,
            (screen.height() - window.height()) // 2
        )
        print(f"  Screen: {screen.width()}x{screen.height()}", flush=True)
        print(f"  Window pos: {window.x()}, {window.y()}", flush=True)
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
    
    print("Step 7: Showing window...", flush=True)
    try:
        window.show()
        window.raise_()  # 최상위로
        window.activateWindow()  # 활성화
        print("  OK", flush=True)
    except Exception as e:
        print(f"  FAILED: {e}", flush=True)
        return 1
    
    print("Step 8: Entering event loop...", flush=True)
    print("="*50, flush=True)
    print("Window should be visible now!", flush=True)
    print("If you don't see it, check taskbar.", flush=True)
    print("Close the window to exit.", flush=True)
    print("="*50, flush=True)
    
    result = app.exec()
    print(f"\nExited with code: {result}", flush=True)
    return result


if __name__ == "__main__":
    sys.exit(main())
