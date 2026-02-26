# -*- mode: python ; coding: utf-8 -*-
"""
Data Graph Studio — PyInstaller spec file

Build:
  pyinstaller dgs.spec

Options:
  --clean     Clean cache before building
  --noconfirm Overwrite output without asking
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# ── 경로 설정 ──
ROOT = Path(SPECPATH)
MAIN_SCRIPT = str(ROOT / "main.py")

# ── Hidden imports ──
# PySide6 플러그인 + polars/pyarrow 내부 모듈은 자동 감지 안 되는 경우 있음
hiddenimports = [
    # PySide6 플러그인
    "PySide6.QtSvg",
    "PySide6.QtSvgWidgets",
    "PySide6.QtPrintSupport",
    # polars 내부
    *collect_submodules("polars"),
    # pyarrow 내부
    *collect_submodules("pyarrow"),
    # pyqtgraph
    *collect_submodules("pyqtgraph"),
    # numpy
    "numpy",
    "numpy.core._methods",
    "numpy.lib.format",
    # 표준 라이브러리 (동적 import)
    "csv",
    "json",
    "sqlite3",
    "decimal",
    "statistics",
    "pydoc",
    # DGS 내부 모듈
    *collect_submodules("data_graph_studio"),
]

# ── 데이터 파일 ──
datas = [
    # polars/pyarrow 데이터 파일
    *collect_data_files("polars"),
    *collect_data_files("pyarrow"),
    *collect_data_files("pyqtgraph"),
]

# ── 제외 모듈 (빌드 크기 축소) ──
excludes = [
    "tkinter",
    "unittest",
    "test",
    "xmlrpc",
    "doctest",
    "pip",
    "setuptools",
    "distutils",
    # 사용하지 않는 Qt 모듈
    "PySide6.QtWebEngine",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebChannel",
    "PySide6.QtQuick",
    "PySide6.QtQuick3D",
    "PySide6.QtQml",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DRender",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DAnimation",
    "PySide6.QtBluetooth",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtPositioning",
    "PySide6.QtRemoteObjects",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTextToSpeech",
    "PySide6.QtWebSockets",
]

# ── Analysis ──
a = Analysis(
    [MAIN_SCRIPT],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ── PYZ (바이트코드 아카이브) ──
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ── EXE ──
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DataGraphStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,                    # UPX 압축 활성화
    # Windows 배포는 디버깅 편의를 위해 콘솔 표시, 그 외 플랫폼은 GUI 전용
    console=(sys.platform == "win32"),
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon="resources/dgs.ico",  # Windows용 아이콘 (있을 때 활성화)
)

# ── COLLECT (onedir 모드) ──
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="DataGraphStudio",
)

# ── macOS .app 번들 (macOS에서만 동작) ──
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="DataGraphStudio.app",
        # icon="resources/dgs.icns",  # macOS용 아이콘 (있을 때 활성화)
        bundle_identifier="com.datagraphstudio.app",
        info_plist={
            "CFBundleName": "Data Graph Studio",
            "CFBundleDisplayName": "Data Graph Studio",
            "CFBundleShortVersionString": "0.15.0",
            "CFBundleVersion": "0.15.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "10.15",
            "NSRequiresAquaSystemAppearance": False,  # 다크모드 지원
        },
    )
