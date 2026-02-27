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

# DirectWrite 폰트 오류 방지 (Windows)
# Qt 초기화 전에 설정해야 함
if sys.platform == 'win32':
    os.environ.setdefault('QT_QPA_PLATFORM', 'windows:fontengine=freetype')

# macOS: Qt 접근성 서브시스템 비활성화
# QAccessibleTree::indexFromLogical 에서 ProjectTreeView 빈 모델 접근 시 segfault 방지
# Ref: https://bugreports.qt.io/browse/QTBUG-104white (PySide6 + QTreeView accessibility crash)
if sys.platform == 'darwin':
    os.environ.setdefault('QT_MAC_WANTS_LAYER', '1')
    os.environ.setdefault('QT_ACCESSIBILITY', '0')

# 로깅 설정
# - 개발 모드: 프로젝트 폴더의 ./logs
# - 배포(Windows Program Files 등): 사용자 쓰기 가능 경로(%LOCALAPPDATA% 등)

def _get_writable_log_dir() -> str:
    # PyInstaller frozen exe (onefile/onedir)일 때는 설치 경로가 Program Files일 수 있어
    # 실행 중 로그/캐시 생성이 PermissionError로 터진다.
    is_frozen = bool(getattr(sys, "frozen", False))

    if sys.platform == "win32" and is_frozen:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "DataGraphStudio", "logs")

    if sys.platform == "darwin" and is_frozen:
        base = os.path.expanduser("~/Library/Logs")
        return os.path.join(base, "DataGraphStudio")

    if sys.platform.startswith("linux") and is_frozen:
        base = os.environ.get("XDG_STATE_HOME") or os.path.expanduser("~/.local/state")
        return os.path.join(base, "data-graph-studio", "logs")

    # Dev / source run
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")


log_dir = _get_writable_log_dir()
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")

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
    """전역 예외 핸들러 — logs to stderr, app log, and ~/.dgs/crash.log"""
    error_msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    logger.critical(f"Unhandled exception:\n{error_msg}")

    # Append to persistent crash log
    try:
        crash_dir = os.path.expanduser("~/.dgs")
        os.makedirs(crash_dir, exist_ok=True)
        crash_path = os.path.join(crash_dir, "crash.log")
        with open(crash_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Timestamp: {datetime.now().isoformat()}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(error_msg)
            f.write(f"{'='*60}\n")
    except OSError:
        pass

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
        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QIcon
        logger.info("PySide6 imported successfully")
        
        # 모듈 임포트 테스트
        logger.info("Importing application modules...")
        from data_graph_studio.ui.main_window import MainWindow
        logger.info("MainWindow imported successfully")
        
        # High DPI 지원
        logger.info("Configuring High DPI...")
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
        
        logger.info("Creating QApplication...")
        app = QApplication(sys.argv)
        
        # 앱 정보
        from data_graph_studio import __version__
        app.setApplicationName("Data Graph Studio")
        app.setApplicationVersion(__version__)
        app.setOrganizationName("Godol")

        # 앱 아이콘 (소스 실행 + PyInstaller 배포 공통)
        base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_dir, "resources", "icons", "dgs.ico")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))
        
        # 기본 폰트
        font = QFont()
        font.setFamily("Helvetica Neue")
        font.setPointSize(10)
        app.setFont(font)
        
        # 스타일
        app.setStyle("Fusion")

        # 스플래시 스크린
        from data_graph_studio.ui.splash_screen import SplashScreen
        splash = SplashScreen(version=__version__)
        splash.show()
        splash.set_status("Loading modules...", 20)

        # 메인 윈도우
        logger.info("Creating MainWindow...")
        splash.set_status("Initializing UI...", 50)
        window = MainWindow()
        logger.info("MainWindow created successfully")

        splash.set_status("Preparing workspace...", 80)
        logger.info("Showing MainWindow...")
        splash.finish(window)
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
