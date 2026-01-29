#!/usr/bin/env python3
"""
Data Graph Studio - Big Data Visualization Tool

Usage:
    python main.py [file_path]
"""

import sys
import os
import traceback
import logging
from datetime import datetime

# 로깅 설정
log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logs')
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
logger = logging.getLogger('DataGraphStudio')

# 프로젝트 루트를 path에 추가
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def exception_hook(exc_type, exc_value, exc_tb):
    """전역 예외 핸들러"""
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"Unhandled exception:\n{error_msg}")
    print(f"\n{'='*60}")
    print("CRITICAL ERROR:")
    print('='*60)
    print(error_msg)
    print('='*60)
    sys.__excepthook__(exc_type, exc_value, exc_tb)


# 전역 예외 핸들러 등록
sys.excepthook = exception_hook


def main():
    logger.info("="*60)
    logger.info("Data Graph Studio Starting...")
    logger.info(f"Python: {sys.version}")
    logger.info(f"Working Dir: {os.getcwd()}")
    logger.info("="*60)
    
    try:
        # Qt 임포트 테스트
        logger.info("Importing PySide6...")
        from PySide6.QtWidgets import QApplication, QMessageBox
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont
        logger.info("PySide6 imported successfully")
        
        # 모듈 임포트 테스트
        logger.info("Importing application modules...")
        from src.ui.main_window import MainWindow
        logger.info("MainWindow imported successfully")
        
        # High DPI 지원
        logger.info("Configuring High DPI...")
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        logger.info("Creating QApplication...")
        app = QApplication(sys.argv)
        
        # 앱 정보
        app.setApplicationName("Data Graph Studio")
        app.setApplicationVersion("0.1.0")
        app.setOrganizationName("Godol")
        
        # 기본 폰트
        font = QFont()
        font.setFamily("Segoe UI")
        font.setPointSize(10)
        app.setFont(font)
        
        # 스타일
        app.setStyle("Fusion")
        
        # 메인 윈도우
        logger.info("Creating MainWindow...")
        window = MainWindow()
        logger.info("MainWindow created successfully")
        
        logger.info("Showing MainWindow...")
        window.show()
        logger.info("MainWindow shown")
        
        # 커맨드라인 인자로 파일 열기
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            if os.path.exists(file_path):
                logger.info(f"Loading file from command line: {file_path}")
                window._load_file(file_path)
        
        logger.info("Entering event loop...")
        result = app.exec()
        logger.info(f"Application exited with code: {result}")
        sys.exit(result)
        
    except ImportError as e:
        error_msg = f"Import Error: {e}\n\n{traceback.format_exc()}"
        logger.critical(error_msg)
        print(f"\n{'='*60}")
        print("IMPORT ERROR - Missing dependencies?")
        print("Run: pip install -r requirements.txt")
        print('='*60)
        print(error_msg)
        sys.exit(1)
        
    except Exception as e:
        error_msg = f"Startup Error: {e}\n\n{traceback.format_exc()}"
        logger.critical(error_msg)
        print(f"\n{'='*60}")
        print("STARTUP ERROR:")
        print('='*60)
        print(error_msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
