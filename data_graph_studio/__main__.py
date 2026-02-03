#!/usr/bin/env python3
"""
Data Graph Studio - Entry point for `python -m data_graph_studio`
"""

import sys
import os
import traceback
import logging
from datetime import datetime

# DirectWrite 폰트 오류 방지 (Windows)
# Qt 초기화 전에 설정해야 함
if sys.platform == 'win32':
    os.environ.setdefault('QT_QPA_PLATFORM', 'windows:fontengine=freetype')


def setup_logging():
    """로깅 설정"""
    log_dir = os.path.join(os.path.expanduser("~"), '.data_graph_studio', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'app_{datetime.now().strftime("%Y%m%d_%H%M%S")}.log')
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )
    return logging.getLogger('DataGraphStudio')


def main():
    import faulthandler
    faulthandler.enable()  # segfault 시 traceback 출력
    
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Data Graph Studio Starting...")
    logger.info(f"Python: {sys.version}")
    logger.info("=" * 60)
    
    try:
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        
        from data_graph_studio.ui.main_window import MainWindow
        
        # High DPI
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        app = QApplication(sys.argv)
        app.setApplicationName("Data Graph Studio")
        app.setApplicationVersion("0.1.0")
        app.setOrganizationName("Godol")
        
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        app.setFont(font)
        app.setStyle("Fusion")
        
        window = MainWindow()
        window.show()
        
        # 커맨드라인 인자
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path):
                window._load_file(file_path)
        
        sys.exit(app.exec())
        
    except ImportError as e:
        logger.critical(f"Import Error: {e}")
        print(f"\nImport Error: {e}")
        print("Run: pip install PySide6 polars pyqtgraph")
        sys.exit(1)
    except Exception as e:
        logger.critical(f"Error: {e}\n{traceback.format_exc()}")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
