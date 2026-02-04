"""
Drawing Module - 그래프 위에 도형/텍스트 그리기 기능

Line, Circle, Rectangle, Text 드로잉 지원
"""

from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid
import math

from PySide6.QtWidgets import (
    QWidget, QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox,
    QColorDialog, QPushButton, QDialogButtonBox, QFontComboBox,
    QTextEdit, QGroupBox, QCheckBox
)
from PySide6.QtCore import Qt, Signal, QPointF, QRectF
from PySide6.QtGui import QColor, QFont, QPen, QBrush, QPainterPath

import pyqtgraph as pg
import numpy as np


# ==================== Drawing Object Types ====================

class DrawingType(Enum):
    """드로잉 객체 타입"""
    LINE = "line"
    CIRCLE = "circle"
    RECT = "rect"
    TEXT = "text"


class LineStyle(Enum):
    """선 스타일"""
    SOLID = "solid"
    DASHED = "dashed"
    DOTTED = "dotted"
    DASH_DOT = "dash_dot"

    def to_qt(self) -> Qt.PenStyle:
        """Convert to Qt pen style"""
        return {
            LineStyle.SOLID: Qt.SolidLine,
            LineStyle.DASHED: Qt.DashLine,
            LineStyle.DOTTED: Qt.DotLine,
            LineStyle.DASH_DOT: Qt.DashDotLine,
        }.get(self, Qt.SolidLine)


# ==================== Drawing Object Dataclasses ====================

@dataclass
class DrawingStyle:
    """공통 드로잉 스타일"""
    stroke_color: str = "#000000"
    stroke_width: float = 1.0
    line_style: LineStyle = LineStyle.SOLID
    fill_color: Optional[str] = None
    fill_opacity: float = 0.3


@dataclass
class DrawingObjectBase:
    """드로잉 객체 기본 클래스"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: DrawingType = DrawingType.LINE
    style: DrawingStyle = field(default_factory=DrawingStyle)
    visible: bool = True
    locked: bool = False
    z_order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """직렬화"""
        data = {
            'id': self.id,
            'type': self.type.value,
            'visible': self.visible,
            'locked': self.locked,
            'z_order': self.z_order,
            'style': {
                'stroke_color': self.style.stroke_color,
                'stroke_width': self.style.stroke_width,
                'line_style': self.style.line_style.value,
                'fill_color': self.style.fill_color,
                'fill_opacity': self.style.fill_opacity,
            }
        }
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DrawingObjectBase':
        """역직렬화"""
        style = DrawingStyle(
            stroke_color=data['style'].get('stroke_color', '#000000'),
            stroke_width=data['style'].get('stroke_width', 2.0),
            line_style=LineStyle(data['style'].get('line_style', 'solid')),
            fill_color=data['style'].get('fill_color'),
            fill_opacity=data['style'].get('fill_opacity', 0.3),
        )
        return cls(
            id=data['id'],
            type=DrawingType(data['type']),
            style=style,
            visible=data.get('visible', True),
            locked=data.get('locked', False),
            z_order=data.get('z_order', 0),
        )


@dataclass
class LineDrawing(DrawingObjectBase):
    """직선 드로잉"""
    type: DrawingType = DrawingType.LINE
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'x1': self.x1, 'y1': self.y1,
            'x2': self.x2, 'y2': self.y2,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LineDrawing':
        base = DrawingObjectBase.from_dict(data)
        return cls(
            id=base.id, type=DrawingType.LINE, style=base.style,
            visible=base.visible, locked=base.locked, z_order=base.z_order,
            x1=data['x1'], y1=data['y1'], x2=data['x2'], y2=data['y2'],
        )

    def get_bounds(self) -> Tuple[float, float, float, float]:
        """Get bounding box (x1, y1, x2, y2)"""
        return (min(self.x1, self.x2), min(self.y1, self.y2),
                max(self.x1, self.x2), max(self.y1, self.y2))

    def move(self, dx: float, dy: float) -> None:
        """Translate the line by (dx, dy)."""
        self.x1 += dx
        self.y1 += dy
        self.x2 += dx
        self.y2 += dy


@dataclass
class CircleDrawing(DrawingObjectBase):
    """원/타원 드로잉"""
    type: DrawingType = DrawingType.CIRCLE
    cx: float = 0.0  # 중심 X
    cy: float = 0.0  # 중심 Y
    rx: float = 1.0  # X 반지름
    ry: float = 1.0  # Y 반지름 (타원용)

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'cx': self.cx, 'cy': self.cy,
            'rx': self.rx, 'ry': self.ry,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CircleDrawing':
        base = DrawingObjectBase.from_dict(data)
        return cls(
            id=base.id, type=DrawingType.CIRCLE, style=base.style,
            visible=base.visible, locked=base.locked, z_order=base.z_order,
            cx=data['cx'], cy=data['cy'], rx=data['rx'], ry=data['ry'],
        )

    def get_bounds(self) -> Tuple[float, float, float, float]:
        return (self.cx - self.rx, self.cy - self.ry,
                self.cx + self.rx, self.cy + self.ry)

    def move(self, dx: float, dy: float) -> None:
        """Translate the circle/ellipse by (dx, dy)."""
        self.cx += dx
        self.cy += dy


@dataclass
class RectDrawing(DrawingObjectBase):
    """사각형 드로잉"""
    type: DrawingType = DrawingType.RECT
    x: float = 0.0
    y: float = 0.0
    width: float = 1.0
    height: float = 1.0
    corner_radius: float = 0.0  # 모서리 둥글기

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'x': self.x, 'y': self.y,
            'width': self.width, 'height': self.height,
            'corner_radius': self.corner_radius,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RectDrawing':
        base = DrawingObjectBase.from_dict(data)
        return cls(
            id=base.id, type=DrawingType.RECT, style=base.style,
            visible=base.visible, locked=base.locked, z_order=base.z_order,
            x=data['x'], y=data['y'],
            width=data['width'], height=data['height'],
            corner_radius=data.get('corner_radius', 0.0),
        )

    def get_bounds(self) -> Tuple[float, float, float, float]:
        return (self.x, self.y, self.x + self.width, self.y + self.height)

    def move(self, dx: float, dy: float) -> None:
        """Translate the rectangle by (dx, dy)."""
        self.x += dx
        self.y += dy


@dataclass
class TextDrawing(DrawingObjectBase):
    """텍스트 드로잉"""
    type: DrawingType = DrawingType.TEXT
    x: float = 0.0
    y: float = 0.0
    text: str = ""
    font_family: str = "Arial"
    font_size: int = 12
    text_color: str = "#000000"
    alignment: str = "left"  # left, center, right
    bold: bool = False
    italic: bool = False

    def to_dict(self) -> Dict[str, Any]:
        data = super().to_dict()
        data.update({
            'x': self.x, 'y': self.y,
            'text': self.text,
            'font_family': self.font_family,
            'font_size': self.font_size,
            'text_color': self.text_color,
            'alignment': self.alignment,
            'bold': self.bold,
            'italic': self.italic,
        })
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextDrawing':
        base = DrawingObjectBase.from_dict(data)
        return cls(
            id=base.id, type=DrawingType.TEXT, style=base.style,
            visible=base.visible, locked=base.locked, z_order=base.z_order,
            x=data['x'], y=data['y'],
            text=data.get('text', ''),
            font_family=data.get('font_family', 'Arial'),
            font_size=data.get('font_size', 12),
            text_color=data.get('text_color', '#000000'),
            alignment=data.get('alignment', 'left'),
            bold=data.get('bold', False),
            italic=data.get('italic', False),
        )

    def get_bounds(self) -> Tuple[float, float, float, float]:
        # Approximate bounds based on text length
        width = len(self.text) * self.font_size * 0.6
        height = self.font_size * 1.2
        return (self.x, self.y - height, self.x + width, self.y)

    def move(self, dx: float, dy: float) -> None:
        """Translate the text by (dx, dy)."""
        self.x += dx
        self.y += dy


# ==================== Helper Functions ====================

def snap_to_angle(x1: float, y1: float, x2: float, y2: float, snap_angle: float = 45.0) -> Tuple[float, float]:
    """
    Snap line endpoint to nearest angle (0, 45, 90, etc.)

    Returns new (x2, y2) snapped to nearest angle
    """
    dx = x2 - x1
    dy = y2 - y1
    length = math.sqrt(dx * dx + dy * dy)

    if length == 0:
        return x2, y2

    # Calculate current angle in degrees
    angle = math.degrees(math.atan2(dy, dx))

    # Snap to nearest multiple of snap_angle
    snapped_angle = round(angle / snap_angle) * snap_angle

    # Convert back to coordinates
    rad = math.radians(snapped_angle)
    new_x2 = x1 + length * math.cos(rad)
    new_y2 = y1 + length * math.sin(rad)

    return new_x2, new_y2


# ==================== Drawing Graphics Items ====================

class LineGraphicsItem(pg.GraphicsObject):
    """PyQtGraph line graphics item"""

    def __init__(self, drawing: LineDrawing):
        super().__init__()
        self.drawing = drawing
        self._selected = False
        self.setZValue(drawing.z_order)

    def boundingRect(self) -> QRectF:
        x1, y1, x2, y2 = self.drawing.get_bounds()
        margin = self.drawing.style.stroke_width
        return QRectF(x1 - margin, y1 - margin,
                     (x2 - x1) + 2 * margin, (y2 - y1) + 2 * margin)

    def paint(self, painter, option, widget):
        if not self.drawing.visible:
            return

        # Set pen
        pen = QPen(QColor(self.drawing.style.stroke_color))
        pen.setWidthF(self.drawing.style.stroke_width)
        pen.setStyle(self.drawing.style.line_style.to_qt())
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Draw line
        painter.drawLine(
            QPointF(self.drawing.x1, self.drawing.y1),
            QPointF(self.drawing.x2, self.drawing.y2)
        )

        # Draw selection handles
        if self._selected:
            self._draw_handles(painter)

    def _draw_handles(self, painter):
        handle_size = 6
        pen = QPen(QColor("#59B8E3"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#323D4A")))

        for x, y in [(self.drawing.x1, self.drawing.y1),
                     (self.drawing.x2, self.drawing.y2)]:
            painter.drawRect(QRectF(
                x - handle_size / 2, y - handle_size / 2,
                handle_size, handle_size
            ))

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()


class CircleGraphicsItem(pg.GraphicsObject):
    """PyQtGraph circle/ellipse graphics item"""

    def __init__(self, drawing: CircleDrawing):
        super().__init__()
        self.drawing = drawing
        self._selected = False
        self.setZValue(drawing.z_order)

    def boundingRect(self) -> QRectF:
        x1, y1, x2, y2 = self.drawing.get_bounds()
        margin = self.drawing.style.stroke_width
        return QRectF(x1 - margin, y1 - margin,
                     (x2 - x1) + 2 * margin, (y2 - y1) + 2 * margin)

    def paint(self, painter, option, widget):
        if not self.drawing.visible:
            return

        # Set pen
        pen = QPen(QColor(self.drawing.style.stroke_color))
        pen.setWidthF(self.drawing.style.stroke_width)
        pen.setStyle(self.drawing.style.line_style.to_qt())
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Set brush (fill)
        if self.drawing.style.fill_color:
            fill = QColor(self.drawing.style.fill_color)
            fill.setAlphaF(self.drawing.style.fill_opacity)
            painter.setBrush(QBrush(fill))
        else:
            painter.setBrush(Qt.NoBrush)

        # Draw ellipse
        painter.drawEllipse(QRectF(
            self.drawing.cx - self.drawing.rx,
            self.drawing.cy - self.drawing.ry,
            self.drawing.rx * 2,
            self.drawing.ry * 2
        ))

        if self._selected:
            self._draw_handles(painter)

    def _draw_handles(self, painter):
        handle_size = 6
        pen = QPen(QColor("#59B8E3"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#323D4A")))

        # Corner handles
        x1, y1, x2, y2 = self.drawing.get_bounds()
        for x, y in [(x1, y1), (x2, y1), (x1, y2), (x2, y2)]:
            painter.drawRect(QRectF(
                x - handle_size / 2, y - handle_size / 2,
                handle_size, handle_size
            ))

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()


class RectGraphicsItem(pg.GraphicsObject):
    """PyQtGraph rectangle graphics item"""

    def __init__(self, drawing: RectDrawing):
        super().__init__()
        self.drawing = drawing
        self._selected = False
        self.setZValue(drawing.z_order)

    def boundingRect(self) -> QRectF:
        margin = self.drawing.style.stroke_width
        return QRectF(
            self.drawing.x - margin,
            self.drawing.y - margin,
            self.drawing.width + 2 * margin,
            self.drawing.height + 2 * margin
        )

    def paint(self, painter, option, widget):
        if not self.drawing.visible:
            return

        # Set pen
        pen = QPen(QColor(self.drawing.style.stroke_color))
        pen.setWidthF(self.drawing.style.stroke_width)
        pen.setStyle(self.drawing.style.line_style.to_qt())
        pen.setCosmetic(True)
        painter.setPen(pen)

        # Set brush (fill)
        if self.drawing.style.fill_color:
            fill = QColor(self.drawing.style.fill_color)
            fill.setAlphaF(self.drawing.style.fill_opacity)
            painter.setBrush(QBrush(fill))
        else:
            painter.setBrush(Qt.NoBrush)

        rect = QRectF(self.drawing.x, self.drawing.y,
                      self.drawing.width, self.drawing.height)

        if self.drawing.corner_radius > 0:
            painter.drawRoundedRect(rect, self.drawing.corner_radius,
                                    self.drawing.corner_radius)
        else:
            painter.drawRect(rect)

        if self._selected:
            self._draw_handles(painter)

    def _draw_handles(self, painter):
        handle_size = 6
        pen = QPen(QColor("#59B8E3"))
        pen.setWidth(2)
        painter.setPen(pen)
        painter.setBrush(QBrush(QColor("#323D4A")))

        x, y = self.drawing.x, self.drawing.y
        w, h = self.drawing.width, self.drawing.height

        for hx, hy in [(x, y), (x + w, y), (x, y + h), (x + w, y + h),
                       (x + w/2, y), (x + w/2, y + h),
                       (x, y + h/2), (x + w, y + h/2)]:
            painter.drawRect(QRectF(
                hx - handle_size / 2, hy - handle_size / 2,
                handle_size, handle_size
            ))

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()


class TextGraphicsItem(pg.TextItem):
    """PyQtGraph text graphics item for drawings"""

    def __init__(self, drawing: TextDrawing):
        # Build font
        font = QFont(drawing.font_family, drawing.font_size)
        if drawing.bold:
            font.setBold(True)
        if drawing.italic:
            font.setItalic(True)

        # Anchor based on alignment
        anchor_map = {
            'left': (0, 1),
            'center': (0.5, 1),
            'right': (1, 1),
        }
        anchor = anchor_map.get(drawing.alignment, (0, 1))

        super().__init__(
            text=drawing.text,
            color=QColor(drawing.text_color),
            anchor=anchor
        )
        self.setFont(font)
        self.setPos(drawing.x, drawing.y)
        self.setZValue(drawing.z_order)

        self.drawing = drawing
        self._selected = False

    def set_selected(self, selected: bool):
        self._selected = selected
        # Could add border when selected
        self.update()


# ==================== Dialogs ====================

class ColorButton(QPushButton):
    """Color picker button"""
    color_changed = Signal(QColor)

    def __init__(self, color: QColor = QColor("#000000"), parent=None):
        super().__init__(parent)
        self._color = color
        self.setFixedSize(28, 28)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Click to choose a color")
        self.clicked.connect(self._on_clicked)
        self._update_style()

    def _update_style(self):
        self.setStyleSheet(f"""
            QPushButton {{
                background: {self._color.name()};
                border: 2px solid #3E4A59;
                border-radius: 4px;
            }}
            QPushButton:hover {{
                border-color: #59B8E3;
            }}
        """)

    def _on_clicked(self):
        color = QColorDialog.getColor(self._color, self, "Select Color")
        if color.isValid():
            self._color = color
            self._update_style()
            self.color_changed.emit(color)

    def color(self) -> QColor:
        return self._color

    def set_color(self, color: QColor):
        self._color = color
        self._update_style()


class DrawingStyleDialog(QDialog):
    """Base dialog for drawing style settings"""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(300)

        self._setup_ui()
        self._apply_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Stroke group
        stroke_group = QGroupBox("Stroke")
        stroke_layout = QGridLayout(stroke_group)

        stroke_layout.addWidget(QLabel("Color:"), 0, 0)
        self.stroke_color_btn = ColorButton(QColor("#000000"))
        stroke_layout.addWidget(self.stroke_color_btn, 0, 1)

        stroke_layout.addWidget(QLabel("Width:"), 1, 0)
        self.stroke_width_spin = QDoubleSpinBox()
        self.stroke_width_spin.setRange(0.5, 20.0)
        self.stroke_width_spin.setValue(2.0)
        self.stroke_width_spin.setSingleStep(0.5)
        self.stroke_width_spin.setToolTip("Set stroke line width")
        stroke_layout.addWidget(self.stroke_width_spin, 1, 1)

        stroke_layout.addWidget(QLabel("Style:"), 2, 0)
        self.line_style_combo = QComboBox()
        self.line_style_combo.setToolTip("Select line dash style")
        self.line_style_combo.addItems(["Solid", "Dashed", "Dotted", "Dash-Dot"])
        stroke_layout.addWidget(self.line_style_combo, 2, 1)

        layout.addWidget(stroke_group)

        # Fill group
        fill_group = QGroupBox("Fill")
        fill_layout = QGridLayout(fill_group)

        self.fill_enabled_check = QCheckBox("Enable Fill")
        self.fill_enabled_check.setToolTip("Enable or disable shape fill")
        fill_layout.addWidget(self.fill_enabled_check, 0, 0, 1, 2)

        fill_layout.addWidget(QLabel("Color:"), 1, 0)
        self.fill_color_btn = ColorButton(QColor("#59B8E3"))
        fill_layout.addWidget(self.fill_color_btn, 1, 1)

        fill_layout.addWidget(QLabel("Opacity:"), 2, 0)
        self.fill_opacity_spin = QDoubleSpinBox()
        self.fill_opacity_spin.setRange(0.0, 1.0)
        self.fill_opacity_spin.setValue(0.3)
        self.fill_opacity_spin.setSingleStep(0.1)
        self.fill_opacity_spin.setToolTip("Set fill opacity (0 = transparent, 1 = opaque)")
        fill_layout.addWidget(self.fill_opacity_spin, 2, 1)

        layout.addWidget(fill_group)
        self.fill_group = fill_group

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def _apply_style(self):
        self.setStyleSheet("""
            QGroupBox {
                font-weight: 600;
                border: 1px solid #3E4A59;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 6px;
            }
        """)

    def get_style(self) -> DrawingStyle:
        """Get the configured drawing style"""
        line_styles = [LineStyle.SOLID, LineStyle.DASHED,
                       LineStyle.DOTTED, LineStyle.DASH_DOT]
        return DrawingStyle(
            stroke_color=self.stroke_color_btn.color().name(),
            stroke_width=self.stroke_width_spin.value(),
            line_style=line_styles[self.line_style_combo.currentIndex()],
            fill_color=self.fill_color_btn.color().name() if self.fill_enabled_check.isChecked() else None,
            fill_opacity=self.fill_opacity_spin.value(),
        )

    def set_style(self, style: DrawingStyle):
        """Set the dialog from a style"""
        self.stroke_color_btn.set_color(QColor(style.stroke_color))
        self.stroke_width_spin.setValue(style.stroke_width)

        style_index = {
            LineStyle.SOLID: 0, LineStyle.DASHED: 1,
            LineStyle.DOTTED: 2, LineStyle.DASH_DOT: 3,
        }.get(style.line_style, 0)
        self.line_style_combo.setCurrentIndex(style_index)

        self.fill_enabled_check.setChecked(style.fill_color is not None)
        if style.fill_color:
            self.fill_color_btn.set_color(QColor(style.fill_color))
        self.fill_opacity_spin.setValue(style.fill_opacity)


class RectStyleDialog(DrawingStyleDialog):
    """Rectangle style dialog with corner radius"""

    def __init__(self, parent=None):
        super().__init__("Rectangle Style", parent)

        # Add corner radius control
        layout = self.layout()

        corner_group = QGroupBox("Corner")
        corner_layout = QGridLayout(corner_group)

        corner_layout.addWidget(QLabel("Radius:"), 0, 0)
        self.corner_radius_spin = QDoubleSpinBox()
        self.corner_radius_spin.setRange(0, 100)
        self.corner_radius_spin.setValue(0)
        self.corner_radius_spin.setToolTip("Set corner rounding radius")
        corner_layout.addWidget(self.corner_radius_spin, 0, 1)

        # Insert before buttons
        layout.insertWidget(layout.count() - 1, corner_group)


class TextInputDialog(QDialog):
    """Text input dialog with font settings"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Text")
        self.setMinimumWidth(400)

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        # Text input
        text_group = QGroupBox("Text")
        text_layout = QVBoxLayout(text_group)

        self.text_edit = QTextEdit()
        self.text_edit.setPlaceholderText("Enter text here...")
        self.text_edit.setMaximumHeight(100)
        text_layout.addWidget(self.text_edit)

        layout.addWidget(text_group)

        # Font settings
        font_group = QGroupBox("Font")
        font_layout = QGridLayout(font_group)

        font_layout.addWidget(QLabel("Family:"), 0, 0)
        self.font_combo = QFontComboBox()
        font_layout.addWidget(self.font_combo, 0, 1)

        font_layout.addWidget(QLabel("Size:"), 1, 0)
        self.size_spin = QSpinBox()
        self.size_spin.setRange(6, 72)
        self.size_spin.setValue(12)
        self.size_spin.setToolTip("Set font size in points")
        font_layout.addWidget(self.size_spin, 1, 1)

        font_layout.addWidget(QLabel("Color:"), 2, 0)
        self.color_btn = ColorButton(QColor("#000000"))
        font_layout.addWidget(self.color_btn, 2, 1)

        # Style checkboxes
        style_layout = QHBoxLayout()
        self.bold_check = QCheckBox("Bold")
        self.bold_check.setToolTip("Toggle bold text style")
        self.italic_check = QCheckBox("Italic")
        self.italic_check.setToolTip("Toggle italic text style")
        style_layout.addWidget(self.bold_check)
        style_layout.addWidget(self.italic_check)
        style_layout.addStretch()
        font_layout.addLayout(style_layout, 3, 0, 1, 2)

        # Alignment
        font_layout.addWidget(QLabel("Align:"), 4, 0)
        self.align_combo = QComboBox()
        self.align_combo.setToolTip("Set text alignment")
        self.align_combo.addItems(["Left", "Center", "Right"])
        font_layout.addWidget(self.align_combo, 4, 1)

        layout.addWidget(font_group)

        # Buttons
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

    def get_text_drawing(self, x: float, y: float) -> TextDrawing:
        """Create TextDrawing from dialog settings"""
        alignment_map = {0: "left", 1: "center", 2: "right"}
        return TextDrawing(
            x=x,
            y=y,
            text=self.text_edit.toPlainText(),
            font_family=self.font_combo.currentFont().family(),
            font_size=self.size_spin.value(),
            text_color=self.color_btn.color().name(),
            alignment=alignment_map.get(self.align_combo.currentIndex(), "left"),
            bold=self.bold_check.isChecked(),
            italic=self.italic_check.isChecked(),
        )


# ==================== Drawing Manager ====================

class DrawingManager:
    """
    드로잉 객체 관리자

    그래프 위에 그려진 객체들을 관리하고,
    저장/불러오기, Undo/Redo 지원
    """

    def __init__(self, plot_widget: pg.PlotWidget):
        self.plot_widget = plot_widget
        self._drawings: List[DrawingObjectBase] = []
        self._graphics_items: Dict[str, pg.GraphicsObject] = {}
        self._selected_id: Optional[str] = None

        # Undo/Redo stacks
        self._undo_stack: List[List[Dict]] = []
        self._redo_stack: List[List[Dict]] = []
        self._max_undo = 50

        # Current drawing style (for new drawings)
        self.current_style = DrawingStyle()

        # Z-order counter
        self._z_counter = 100  # Start above data plots

    def add_drawing(self, drawing: DrawingObjectBase) -> str:
        """Add a drawing object"""
        # Save state for undo
        self._save_undo_state()

        # Set z-order
        drawing.z_order = self._z_counter
        self._z_counter += 1

        self._drawings.append(drawing)
        self._create_graphics_item(drawing)

        return drawing.id

    def remove_drawing(self, drawing_id: str) -> bool:
        """Remove a drawing by ID"""
        for i, drawing in enumerate(self._drawings):
            if drawing.id == drawing_id:
                # Save state for undo
                self._save_undo_state()

                # Remove graphics item
                if drawing_id in self._graphics_items:
                    self.plot_widget.removeItem(self._graphics_items[drawing_id])
                    del self._graphics_items[drawing_id]

                # Remove from list
                self._drawings.pop(i)

                if self._selected_id == drawing_id:
                    self._selected_id = None

                return True
        return False

    def get_drawing(self, drawing_id: str) -> Optional[DrawingObjectBase]:
        """Get a drawing by ID"""
        for drawing in self._drawings:
            if drawing.id == drawing_id:
                return drawing
        return None

    def get_all_drawings(self) -> List[DrawingObjectBase]:
        """Get all drawings"""
        return self._drawings.copy()

    def select_drawing(self, drawing_id: Optional[str]):
        """Select a drawing"""
        # Deselect previous
        if self._selected_id and self._selected_id in self._graphics_items:
            item = self._graphics_items[self._selected_id]
            if hasattr(item, 'set_selected'):
                item.set_selected(False)

        self._selected_id = drawing_id

        # Select new
        if drawing_id and drawing_id in self._graphics_items:
            item = self._graphics_items[drawing_id]
            if hasattr(item, 'set_selected'):
                item.set_selected(True)

    def get_selected_id(self) -> Optional[str]:
        """Get selected drawing ID"""
        return self._selected_id

    def delete_selected(self) -> bool:
        """Delete the selected drawing"""
        if self._selected_id:
            return self.remove_drawing(self._selected_id)
        return False

    def _create_graphics_item(self, drawing: DrawingObjectBase):
        """Create graphics item for a drawing"""
        item = None

        if isinstance(drawing, LineDrawing):
            item = LineGraphicsItem(drawing)
        elif isinstance(drawing, CircleDrawing):
            item = CircleGraphicsItem(drawing)
        elif isinstance(drawing, RectDrawing):
            item = RectGraphicsItem(drawing)
        elif isinstance(drawing, TextDrawing):
            item = TextGraphicsItem(drawing)

        if item:
            self.plot_widget.addItem(item)
            self._graphics_items[drawing.id] = item

    def _remove_all_graphics_items(self):
        """Remove all graphics items from plot"""
        for item in self._graphics_items.values():
            self.plot_widget.removeItem(item)
        self._graphics_items.clear()

    def _recreate_all_graphics_items(self):
        """Recreate all graphics items"""
        self._remove_all_graphics_items()
        for drawing in self._drawings:
            self._create_graphics_item(drawing)

    def update_drawing(self, drawing: DrawingObjectBase):
        """Update a drawing's graphics"""
        if drawing.id in self._graphics_items:
            self.plot_widget.removeItem(self._graphics_items[drawing.id])
            del self._graphics_items[drawing.id]
        self._create_graphics_item(drawing)

    # ==================== Undo/Redo ====================

    def _save_undo_state(self):
        """Save current state to undo stack"""
        state = [d.to_dict() for d in self._drawings]
        self._undo_stack.append(state)

        # Limit stack size
        if len(self._undo_stack) > self._max_undo:
            self._undo_stack.pop(0)

        # Clear redo stack on new action
        self._redo_stack.clear()

    def undo(self) -> bool:
        """Undo last action"""
        if not self._undo_stack:
            return False

        # Save current state to redo
        current = [d.to_dict() for d in self._drawings]
        self._redo_stack.append(current)

        # Restore previous state
        prev_state = self._undo_stack.pop()
        self._restore_state(prev_state)

        return True

    def redo(self) -> bool:
        """Redo last undone action"""
        if not self._redo_stack:
            return False

        # Save current state to undo
        current = [d.to_dict() for d in self._drawings]
        self._undo_stack.append(current)

        # Restore redo state
        next_state = self._redo_stack.pop()
        self._restore_state(next_state)

        return True

    def _restore_state(self, state: List[Dict]):
        """Restore drawings from state"""
        self._remove_all_graphics_items()
        self._drawings.clear()

        for data in state:
            drawing = self._deserialize_drawing(data)
            if drawing:
                self._drawings.append(drawing)
                self._create_graphics_item(drawing)

    # ==================== Serialization ====================

    def to_dict(self) -> Dict[str, Any]:
        """Serialize all drawings to dict"""
        return {
            'drawings': [d.to_dict() for d in self._drawings],
            'z_counter': self._z_counter,
        }

    def from_dict(self, data: Dict[str, Any]):
        """Deserialize drawings from dict"""
        self.clear()

        self._z_counter = data.get('z_counter', 100)

        for d_data in data.get('drawings', []):
            drawing = self._deserialize_drawing(d_data)
            if drawing:
                self._drawings.append(drawing)
                self._create_graphics_item(drawing)

    def _deserialize_drawing(self, data: Dict) -> Optional[DrawingObjectBase]:
        """Deserialize a single drawing"""
        drawing_type = data.get('type')

        try:
            if drawing_type == 'line':
                return LineDrawing.from_dict(data)
            elif drawing_type == 'circle':
                return CircleDrawing.from_dict(data)
            elif drawing_type == 'rect':
                return RectDrawing.from_dict(data)
            elif drawing_type == 'text':
                return TextDrawing.from_dict(data)
        except Exception as e:
            print(f"Error deserializing drawing: {e}")
            return None

        return None

    def clear(self):
        """Clear all drawings"""
        self._remove_all_graphics_items()
        self._drawings.clear()
        self._selected_id = None
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ==================== Hit Testing ====================

    def find_drawing_at(self, x: float, y: float, tolerance: float = 5.0) -> Optional[str]:
        """Find a drawing at the given position"""
        # Check in reverse order (top to bottom)
        for drawing in reversed(self._drawings):
            if not drawing.visible:
                continue

            bounds = drawing.get_bounds()
            x1, y1, x2, y2 = bounds

            # Expand bounds by tolerance
            if (x1 - tolerance <= x <= x2 + tolerance and
                y1 - tolerance <= y <= y2 + tolerance):
                return drawing.id

        return None
