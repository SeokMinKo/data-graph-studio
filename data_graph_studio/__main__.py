#!/usr/bin/env python3
"""
Data Graph Studio - Entry point for `python -m data_graph_studio`
"""

import sys
import os
import argparse
import traceback
import logging
from datetime import datetime

# DirectWrite 폰트 오류 방지 (Windows)
# Qt 초기화 전에 설정해야 함
if sys.platform == "win32":
    os.environ.setdefault("QT_QPA_PLATFORM", "windows:fontengine=freetype")


def setup_logging():
    """로깅 설정"""
    log_dir = os.path.join(os.path.expanduser("~"), ".data_graph_studio", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"app_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )
    return logging.getLogger("DataGraphStudio")


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Data Graph Studio")
    parser.add_argument("files", nargs="*", help="Files to open")
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode (enables IPC execute handler)",
    )
    return parser.parse_args()


def main():
    import faulthandler

    faulthandler.enable()  # segfault 시 traceback 출력

    args = parse_args()
    logger = setup_logging()
    logger.info("=" * 60)
    logger.info("Data Graph Studio Starting...")
    logger.info(f"Python: {sys.version}")
    if args.debug:
        logger.info("Debug mode enabled")
    logger.info("=" * 60)

    try:
        from data_graph_studio.core.ipc_server import (
            is_another_instance_running,
            send_files_to_existing_instance,
        )

        # Single-instance protection
        file_paths = [f for f in args.files if os.path.exists(f)]
        if is_another_instance_running():
            logger.info("Another instance is running, forwarding files...")
            if file_paths:
                send_files_to_existing_instance(file_paths)
            else:
                logger.info("No files to forward, exiting.")
            sys.exit(0)

        from PySide6.QtWidgets import QApplication
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QFont, QFontDatabase

        from data_graph_studio.ui.main_window import MainWindow

        # High DPI
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )

        app = QApplication(sys.argv)
        app.setApplicationName("Data Graph Studio")
        app.setApplicationVersion("0.1.0")
        app.setOrganizationName("Godol")

        # Use platform-safe default UI font with Korean fallback.
        preferred_fonts = [
            "Segoe UI",  # Windows
            "Malgun Gothic",  # Windows Korean
            "Apple SD Gothic Neo",  # macOS Korean
            "Noto Sans CJK KR",  # Linux/packaged CJK
            "Noto Sans",
            "Helvetica Neue",
            "Arial",
        ]
        available = set(QFontDatabase.families())
        chosen = next((f for f in preferred_fonts if f in available), None)

        font = QFont()
        if chosen:
            font.setFamily(chosen)
        font.setPointSize(10)
        app.setFont(font)
        app.setStyle("Fusion")

        logger.info("UI font selected: %s", chosen or "Qt default")

        window = MainWindow(debug=args.debug)
        window.show()

        # 커맨드라인 인자로 파일 로드
        for file_path in file_paths:
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
