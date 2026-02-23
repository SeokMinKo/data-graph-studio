"""
Export Controller Tests — PRD Feature 4 (Export Enhancement)

UT-4.1: PNG 내보내기 파일 생성
UT-4.2: SVG 내보내기 파일 생성
UT-4.3: PDF 내보내기 파일 생성
UT-4.4: 원자적 저장 (temp → rename)
UT-4.5: 내보내기 취소 시 부분 파일 삭제
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional
from unittest.mock import patch

import pytest

# Ensure headless Qt before any PySide6 import
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_app: Optional[QApplication] = None


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """Create a QApplication once for the whole session."""
    global _app
    if QApplication.instance() is None:
        _app = QApplication([])
    else:
        _app = QApplication.instance()
    return _app


@pytest.fixture
def tmp_dir(tmp_path):
    """Provide a temporary directory."""
    return tmp_path


@pytest.fixture
def sample_qimage() -> QImage:
    """Create a simple 100x100 test QImage."""
    img = QImage(100, 100, QImage.Format_ARGB32)
    img.fill(QColor(255, 0, 0))
    painter = QPainter(img)
    painter.setPen(QColor(0, 0, 255))
    painter.drawLine(0, 0, 100, 100)
    painter.end()
    return img


@pytest.fixture
def sample_svg_bytes() -> bytes:
    """Create minimal SVG bytes."""
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">'
        '<rect fill="red" width="100" height="100"/>'
        '</svg>'
    )
    return svg.encode("utf-8")


# ---------------------------------------------------------------------------
# Import ExportController and friends
# ---------------------------------------------------------------------------
from data_graph_studio.core.export_controller import (
    ExportController,
    ExportFormat,
    ExportOptions,
)
from data_graph_studio.core.io_abstract import atomic_write
from data_graph_studio.ui.renderers.qt_export_renderer import QtExportRenderer


@pytest.fixture(scope="session")
def qt_renderer():
    """Provide a QtExportRenderer for chart export tests."""
    return QtExportRenderer()


# ===========================================================================
# UT-4.1  PNG 내보내기 파일 생성
# ===========================================================================

class TestPNGExport:
    """UT-4.1: PNG export produces a valid file."""

    def test_export_png_creates_file(self, tmp_dir, sample_qimage, qt_renderer):
        """PNG export should create a .png file at the requested path."""
        out_path = str(tmp_dir / "chart.png")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
        # File should start with PNG magic bytes
        with open(out_path, "rb") as f:
            magic = f.read(8)
        assert magic[:4] == b"\x89PNG"

    def test_export_png_custom_resolution(self, tmp_dir, sample_qimage, qt_renderer):
        """PNG export with custom resolution (1920×1080)."""
        out_path = str(tmp_dir / "chart_hd.png")
        opts = ExportOptions(width=1920, height=1080)
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
            options=opts,
        )
        assert os.path.exists(out_path)
        # Verify dimensions by reading back
        result_img = QImage(out_path)
        assert result_img.width() == 1920
        assert result_img.height() == 1080

    def test_export_png_4k_resolution(self, tmp_dir, sample_qimage, qt_renderer):
        """PNG export with 4K resolution (3840×2160)."""
        out_path = str(tmp_dir / "chart_4k.png")
        opts = ExportOptions(width=3840, height=2160)
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
            options=opts,
        )
        assert os.path.exists(out_path)
        result_img = QImage(out_path)
        assert result_img.width() == 3840
        assert result_img.height() == 2160

    def test_export_png_transparent_background(self, tmp_dir, qt_renderer):
        """PNG export with transparent background."""
        img = QImage(100, 100, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        out_path = str(tmp_dir / "transparent.png")
        opts = ExportOptions(background="transparent")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(image=img, path=out_path, fmt=ExportFormat.PNG, options=opts)
        assert os.path.exists(out_path)


# ===========================================================================
# UT-4.2  SVG 내보내기 파일 생성
# ===========================================================================

class TestSVGExport:
    """UT-4.2: SVG export produces a valid file."""

    def test_export_svg_creates_file(self, tmp_dir, sample_qimage, qt_renderer):
        """SVG export should create a .svg file."""
        out_path = str(tmp_dir / "chart.svg")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.SVG,
        )
        assert os.path.exists(out_path)
        content = Path(out_path).read_text(encoding="utf-8")
        assert "<svg" in content.lower()

    def test_export_svg_is_valid_xml(self, tmp_dir, sample_qimage, qt_renderer):
        """SVG output should be well-formed XML."""
        import xml.etree.ElementTree as ET
        out_path = str(tmp_dir / "chart_valid.svg")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.SVG,
        )
        tree = ET.parse(out_path)
        root = tree.getroot()
        assert "svg" in root.tag.lower()


# ===========================================================================
# UT-4.3  PDF 내보내기 파일 생성
# ===========================================================================

class TestPDFExport:
    """UT-4.3: PDF export produces a valid file."""

    def test_export_pdf_creates_file(self, tmp_dir, sample_qimage, qt_renderer):
        """PDF export should create a .pdf file."""
        out_path = str(tmp_dir / "chart.pdf")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PDF,
        )
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0
        # PDF magic bytes
        with open(out_path, "rb") as f:
            magic = f.read(5)
        assert magic == b"%PDF-"

    def test_export_pdf_a4_size(self, tmp_dir, sample_qimage, qt_renderer):
        """PDF with A4 page size."""
        out_path = str(tmp_dir / "chart_a4.pdf")
        opts = ExportOptions(page_size="A4")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PDF,
            options=opts,
        )
        assert os.path.exists(out_path)
        with open(out_path, "rb") as f:
            assert f.read(5) == b"%PDF-"

    def test_export_pdf_letter_size(self, tmp_dir, sample_qimage, qt_renderer):
        """PDF with Letter page size."""
        out_path = str(tmp_dir / "chart_letter.pdf")
        opts = ExportOptions(page_size="Letter")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PDF,
            options=opts,
        )
        assert os.path.exists(out_path)

    def test_export_pdf_with_stats(self, tmp_dir, sample_qimage, qt_renderer):
        """PDF with statistics summary included."""
        out_path = str(tmp_dir / "chart_stats.pdf")
        stats = {
            "mean": 42.5,
            "median": 40.0,
            "std": 5.2,
            "min": 30.0,
            "max": 55.0,
            "count": 100,
        }
        opts = ExportOptions(page_size="A4", include_stats=True, stats_data=stats)
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PDF,
            options=opts,
        )
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 100  # Should be non-trivial


# ===========================================================================
# UT-4.4  원자적 저장 (temp → rename)
# ===========================================================================

class TestAtomicExport:
    """UT-4.4: Exports use atomic write (temp → rename)."""

    def test_atomic_write_creates_final_no_tmp(self, tmp_dir):
        """After atomic_write, only the final file exists (no .tmp)."""
        out_path = str(tmp_dir / "atomic_test.bin")
        data = b"Hello atomic world"
        atomic_write(out_path, data)
        assert os.path.exists(out_path)
        assert not os.path.exists(out_path + ".tmp")
        assert Path(out_path).read_bytes() == data

    def test_export_png_uses_atomic_write(self, tmp_dir, sample_qimage, qt_renderer):
        """PNG export should use atomic write — no .tmp left behind."""
        out_path = str(tmp_dir / "atomic_chart.png")
        ctrl = ExportController(renderer=qt_renderer)
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        assert os.path.exists(out_path)
        assert not os.path.exists(out_path + ".tmp")

    def test_atomic_write_cleans_tmp_on_failure(self, tmp_dir):
        """If atomic_write fails, the .tmp file is cleaned up."""
        out_path = str(tmp_dir / "fail_test.bin")
        # Simulate failure by writing to a read-only directory
        # Instead: patch os.rename to raise
        with patch("data_graph_studio.core.io_abstract.os.rename", side_effect=OSError("rename failed")):
            with pytest.raises(OSError):
                atomic_write(out_path, b"data")
        assert not os.path.exists(out_path + ".tmp")

    def test_export_uses_temp_rename_pattern(self, tmp_dir, sample_qimage, qt_renderer):
        """Verify export writes to .tmp first, then renames (checked via controller internals)."""
        out_path = str(tmp_dir / "pattern_test.png")
        rename_calls = []

        original_rename = os.rename

        def tracking_rename(src, dst):
            rename_calls.append((src, dst))
            return original_rename(src, dst)

        ctrl = ExportController(renderer=qt_renderer)
        with patch("data_graph_studio.core.export_workers.os.rename", tracking_rename):
            ctrl.export_chart_sync(
                image=sample_qimage,
                path=out_path,
                fmt=ExportFormat.PNG,
            )

        # At least one rename from .tmp to final
        assert any(
            src.endswith(".tmp") and dst == out_path
            for src, dst in rename_calls
        )


# ===========================================================================
# UT-4.5  내보내기 취소 시 부분 파일 삭제
# ===========================================================================

class TestExportCancel:
    """UT-4.5: Cancel during export cleans up partial files."""

    def test_cancel_flag_stops_export(self, tmp_dir, sample_qimage, qt_renderer):
        """Setting _cancelled should stop the worker and delete partial file."""
        out_path = str(tmp_dir / "cancel_test.png")
        ctrl = ExportController(renderer=qt_renderer)
        # Pre-cancel before running
        ctrl.cancel()

        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        # File should NOT exist (cancelled)
        assert not os.path.exists(out_path)

    def test_cancel_deletes_tmp_file(self, tmp_dir, sample_qimage, qt_renderer):
        """If tmp file was partially written when cancel hits, it should be cleaned."""
        out_path = str(tmp_dir / "cancel_tmp_test.png")
        tmp_file = out_path + ".tmp"

        # Create a partial tmp file to simulate mid-write cancel
        Path(tmp_file).write_bytes(b"partial data")
        assert os.path.exists(tmp_file)

        ctrl = ExportController(renderer=qt_renderer)
        ctrl.cancel()
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        # Both final and tmp should be cleaned
        assert not os.path.exists(out_path)
        assert not os.path.exists(tmp_file)

    def test_cancel_reset_allows_next_export(self, tmp_dir, sample_qimage, qt_renderer):
        """After cancel + reset, the next export should succeed."""
        out_path = str(tmp_dir / "reset_test.png")
        ctrl = ExportController(renderer=qt_renderer)

        # Cancel then reset
        ctrl.cancel()
        ctrl.reset()

        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        assert os.path.exists(out_path)


# ===========================================================================
# Data Export Tests (FR-4.4)
# ===========================================================================

class TestDataExport:
    """FR-4.4: Data export to CSV/Parquet/Excel."""

    def test_export_csv(self, tmp_dir):
        """Export DataFrame to CSV."""
        import polars as pl

        df = pl.DataFrame({"a": [1, 2, 3], "b": [4.0, 5.0, 6.0]})
        out_path = str(tmp_dir / "data.csv")
        ctrl = ExportController()
        ctrl.export_data_sync(df=df, path=out_path, fmt=ExportFormat.CSV)
        assert os.path.exists(out_path)
        loaded = pl.read_csv(out_path)
        assert loaded.shape == (3, 2)
        assert loaded["a"].to_list() == [1, 2, 3]

    def test_export_parquet(self, tmp_dir):
        """Export DataFrame to Parquet."""
        import polars as pl

        df = pl.DataFrame({"x": [10, 20], "y": ["a", "b"]})
        out_path = str(tmp_dir / "data.parquet")
        ctrl = ExportController()
        ctrl.export_data_sync(df=df, path=out_path, fmt=ExportFormat.PARQUET)
        assert os.path.exists(out_path)
        loaded = pl.read_parquet(out_path)
        assert loaded.shape == (2, 2)

    def test_export_excel(self, tmp_dir):
        """Export DataFrame to Excel."""
        import polars as pl

        df = pl.DataFrame({"col1": [1, 2], "col2": [3, 4]})
        out_path = str(tmp_dir / "data.xlsx")
        ctrl = ExportController()
        ctrl.export_data_sync(df=df, path=out_path, fmt=ExportFormat.EXCEL)
        assert os.path.exists(out_path)
        assert os.path.getsize(out_path) > 0


# ===========================================================================
# ExportOptions Tests
# ===========================================================================

class TestExportOptions:
    """Test ExportOptions dataclass defaults and configuration."""

    def test_default_options(self):
        opts = ExportOptions()
        assert opts.width is None
        assert opts.height is None
        assert opts.dpi == 96
        assert opts.background == "white"
        assert opts.include_legend is True
        assert opts.include_stats is False
        assert opts.page_size == "A4"

    def test_custom_options(self):
        opts = ExportOptions(
            width=1920,
            height=1080,
            dpi=150,
            background="transparent",
            include_legend=False,
            include_stats=True,
            page_size="Letter",
        )
        assert opts.width == 1920
        assert opts.height == 1080
        assert opts.dpi == 150
        assert opts.background == "transparent"
        assert opts.include_legend is False
        assert opts.include_stats is True
        assert opts.page_size == "Letter"


# ===========================================================================
# Signal Tests (progress_changed, export_completed, export_failed)
# ===========================================================================

class TestExportSignals:
    """Test that ExportController emits proper signals."""

    def test_progress_signal(self, tmp_dir, sample_qimage, qapp, qt_renderer):
        """progress_changed event should fire during export."""
        out_path = str(tmp_dir / "signal_test.png")
        ctrl = ExportController(renderer=qt_renderer)
        progress_values = []

        ctrl.subscribe("progress_changed", lambda v: progress_values.append(v))
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        # Should have received at least start (0) and end (100)
        assert len(progress_values) >= 1
        assert max(progress_values) == 100

    def test_completed_signal(self, tmp_dir, sample_qimage, qapp, qt_renderer):
        """export_completed should fire with the output path."""
        out_path = str(tmp_dir / "complete_test.png")
        ctrl = ExportController(renderer=qt_renderer)
        completed_paths = []

        ctrl.subscribe("export_completed", lambda p: completed_paths.append(p))
        ctrl.export_chart_sync(
            image=sample_qimage,
            path=out_path,
            fmt=ExportFormat.PNG,
        )
        assert out_path in completed_paths

    def test_failed_signal_on_error(self, tmp_dir, qapp, qt_renderer):
        """export_failed should fire if an error occurs."""
        # Export with invalid image to trigger error
        ctrl = ExportController(renderer=qt_renderer)
        errors = []
        ctrl.subscribe("export_failed", lambda e: errors.append(e))

        # Null image should fail
        ctrl.export_chart_sync(
            image=QImage(),
            path=str(tmp_dir / "fail.png"),
            fmt=ExportFormat.PNG,
        )
        assert len(errors) >= 1


# ===========================================================================
# ExportFormat enum
# ===========================================================================

class TestExportFormat:
    """ExportFormat enum should have all required formats."""

    def test_chart_formats(self):
        assert ExportFormat.PNG is not None
        assert ExportFormat.SVG is not None
        assert ExportFormat.PDF is not None

    def test_data_formats(self):
        assert ExportFormat.CSV is not None
        assert ExportFormat.PARQUET is not None
        assert ExportFormat.EXCEL is not None
