"""Qt implementation of IExportRenderer using QPainter and QSvgGenerator."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QMarginsF, QRectF, QSize, QRect
from PySide6.QtGui import QImage, QPainter, QColor, QFont, QPageSize, QPdfWriter
from PySide6.QtSvg import QSvgGenerator

from data_graph_studio.core.io_abstract import IExportRenderer


class QtExportRenderer(IExportRenderer):
    """Renders Qt QImage objects to image formats using QPainter."""

    def render_to_png(self, widget: Any, width: int, height: int, dpi: int = 96) -> bytes:
        """Render a QImage to PNG bytes using QImage + QPainter.

        Args:
            widget: A QImage instance to render.
            width: Output width in pixels.
            height: Output height in pixels.
            dpi: Dots per inch (unused for PNG but kept for interface compat).

        Returns:
            PNG image as bytes.
        """
        img: QImage = widget

        if width and height:
            from PySide6.QtCore import Qt
            img = img.scaled(
                width,
                height,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)
        img.save(qbuf, "PNG")
        qbuf.close()
        return bytes(qba.data())

    def render_to_png_with_background(
        self, widget: Any, width: int, height: int, background: str, dpi: int = 96
    ) -> bytes:
        """Render a QImage to PNG bytes, applying a background colour first.

        Args:
            widget: A QImage instance to render.
            width: Output width in pixels (0 = keep original).
            height: Output height in pixels (0 = keep original).
            background: "transparent" | "white" | "dark" | "#rrggbb".
            dpi: Dots per inch.

        Returns:
            PNG image as bytes.
        """
        img: QImage = widget

        if width and height:
            from PySide6.QtCore import Qt
            img = img.scaled(
                width,
                height,
                Qt.IgnoreAspectRatio,
                Qt.SmoothTransformation,
            )

        if background == "transparent":
            pass
        elif background == "white":
            img = self._apply_background(img, QColor(255, 255, 255))
        elif background == "dark":
            img = self._apply_background(img, QColor(43, 52, 64))
        elif background.startswith("#"):
            img = self._apply_background(img, QColor(background))

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)
        img.save(qbuf, "PNG")
        qbuf.close()
        return bytes(qba.data())

    def render_to_svg(self, widget: Any, width: int, height: int) -> bytes:
        """Render a QImage to SVG bytes using QSvgGenerator.

        Args:
            widget: A QImage instance to render.
            width: Output width in pixels.
            height: Output height in pixels.

        Returns:
            SVG XML as bytes.
        """
        img: QImage = widget

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)

        gen = QSvgGenerator()
        gen.setOutputDevice(qbuf)
        gen.setSize(QSize(width, height))
        gen.setViewBox(QRect(0, 0, width, height))
        gen.setTitle("Data Graph Studio Export")
        gen.setDescription("Chart exported by Data Graph Studio")

        painter = QPainter()
        painter.begin(gen)
        target = painter.viewport()
        painter.drawImage(target, img)
        painter.end()
        qbuf.close()

        return bytes(qba.data())

    def render_to_pdf(self, widget: Any, width: int, height: int, options=None) -> bytes:
        """Render a QImage to PDF bytes using QPdfWriter and QPainter.

        Args:
            widget: A QImage instance to render.
            width: Output width in pixels (unused — PDF uses page dimensions).
            height: Output height in pixels (unused — PDF uses page dimensions).
            options: ExportOptions instance (dpi, page_size, include_stats, stats_data).

        Returns:
            PDF document as bytes.
        """
        img: QImage = widget

        dpi = 96
        page_size_str = "A4"
        include_stats = False
        stats_data = None

        if options is not None:
            dpi = getattr(options, "dpi", 96)
            page_size_str = getattr(options, "page_size", "A4")
            include_stats = getattr(options, "include_stats", False)
            stats_data = getattr(options, "stats_data", None)

        qba = QByteArray()
        qbuf = QBuffer(qba)
        qbuf.open(QIODevice.WriteOnly)

        writer = QPdfWriter(qbuf)

        if page_size_str.upper() == "LETTER":
            writer.setPageSize(QPageSize(QPageSize.Letter))
        else:
            writer.setPageSize(QPageSize(QPageSize.A4))

        writer.setPageMargins(QMarginsF(20, 20, 20, 20))
        writer.setResolution(dpi)

        painter = QPainter()
        painter.begin(writer)

        page_rect = painter.viewport()
        margin = 40
        chart_rect = QRectF(
            margin,
            margin,
            page_rect.width() - 2 * margin,
            page_rect.height() * 0.6 - margin,
        )
        painter.drawImage(chart_rect.toRect(), img)

        if include_stats and stats_data:
            y_offset = int(chart_rect.bottom()) + 40

            font = QFont("Helvetica", 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(margin, y_offset, "Statistics Summary")
            y_offset += 30

            font.setBold(False)
            font.setPointSize(10)
            painter.setFont(font)

            for key, value in stats_data.items():
                if isinstance(value, float):
                    text = f"{key}: {value:.4f}"
                else:
                    text = f"{key}: {value}"
                painter.drawText(margin + 10, y_offset, text)
                y_offset += 22

        painter.end()
        qbuf.close()

        return bytes(qba.data())

    @staticmethod
    def _apply_background(img: QImage, color: QColor) -> QImage:
        """Composite the image over a solid background colour."""
        result = QImage(img.size(), QImage.Format_ARGB32)
        result.fill(color)
        painter = QPainter(result)
        painter.drawImage(0, 0, img)
        painter.end()
        return result
