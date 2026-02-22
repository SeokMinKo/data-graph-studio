"""Qt implementation of IExportRenderer using QPainter and QSvgGenerator."""
from __future__ import annotations

from typing import Any

from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, QRect
from PySide6.QtGui import QImage, QPainter, QColor
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

    @staticmethod
    def _apply_background(img: QImage, color: QColor) -> QImage:
        """Composite the image over a solid background colour."""
        result = QImage(img.size(), QImage.Format_ARGB32)
        result.fill(color)
        painter = QPainter(result)
        painter.drawImage(0, 0, img)
        painter.end()
        return result
