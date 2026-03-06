"""
Tests for Drawing functionality
"""

import pytest
from unittest.mock import MagicMock

# Test drawing module imports
from data_graph_studio.ui.drawing import (
    DrawingType,
    LineStyle,
    DrawingStyle,
    LineDrawing,
    CircleDrawing,
    RectDrawing,
    TextDrawing,
    DrawingManager,
    snap_to_angle,
)
from data_graph_studio.core.state import ToolMode


class TestLineStyle:
    """Test LineStyle enum"""

    def test_line_styles_exist(self):
        """Test that all line styles are defined"""
        assert LineStyle.SOLID.value == "solid"
        assert LineStyle.DASHED.value == "dashed"
        assert LineStyle.DOTTED.value == "dotted"
        assert LineStyle.DASH_DOT.value == "dash_dot"

    def test_to_qt(self):
        """Test conversion to Qt pen style"""
        from PySide6.QtCore import Qt

        assert LineStyle.SOLID.to_qt() == Qt.SolidLine
        assert LineStyle.DASHED.to_qt() == Qt.DashLine
        assert LineStyle.DOTTED.to_qt() == Qt.DotLine
        assert LineStyle.DASH_DOT.to_qt() == Qt.DashDotLine


class TestDrawingStyle:
    """Test DrawingStyle dataclass"""

    def test_default_style(self):
        """Test default style values"""
        style = DrawingStyle()
        assert style.stroke_color == "#000000"
        assert style.stroke_width == 1.0
        assert style.line_style == LineStyle.SOLID
        assert style.fill_color is None
        assert style.fill_opacity == 0.3

    def test_custom_style(self):
        """Test custom style values"""
        style = DrawingStyle(
            stroke_color="#FF0000",
            stroke_width=5.0,
            line_style=LineStyle.DASHED,
            fill_color="#00FF00",
            fill_opacity=0.5,
        )
        assert style.stroke_color == "#FF0000"
        assert style.stroke_width == 5.0
        assert style.line_style == LineStyle.DASHED
        assert style.fill_color == "#00FF00"
        assert style.fill_opacity == 0.5


class TestLineDrawing:
    """Test LineDrawing class"""

    def test_create_line(self):
        """Test creating a line drawing"""
        line = LineDrawing(x1=0, y1=0, x2=10, y2=10)
        assert line.type == DrawingType.LINE
        assert line.x1 == 0
        assert line.y1 == 0
        assert line.x2 == 10
        assert line.y2 == 10

    def test_line_bounds(self):
        """Test line bounding box calculation"""
        line = LineDrawing(x1=5, y1=10, x2=15, y2=20)
        bounds = line.get_bounds()
        assert bounds == (5, 10, 15, 20)

        # Test with reversed points
        line2 = LineDrawing(x1=15, y1=20, x2=5, y2=10)
        bounds2 = line2.get_bounds()
        assert bounds2 == (5, 10, 15, 20)

    def test_line_serialization(self):
        """Test line serialization/deserialization"""
        style = DrawingStyle(stroke_color="#FF0000", stroke_width=3.0)
        line = LineDrawing(
            id="test123",
            x1=0,
            y1=0,
            x2=100,
            y2=100,
            style=style,
            visible=True,
            locked=False,
        )

        data = line.to_dict()
        assert data["type"] == "line"
        assert data["x1"] == 0
        assert data["x2"] == 100
        assert data["style"]["stroke_color"] == "#FF0000"

        # Deserialize
        restored = LineDrawing.from_dict(data)
        assert restored.id == "test123"
        assert restored.x1 == 0
        assert restored.x2 == 100
        assert restored.style.stroke_color == "#FF0000"


class TestCircleDrawing:
    """Test CircleDrawing class"""

    def test_create_circle(self):
        """Test creating a circle drawing"""
        circle = CircleDrawing(cx=50, cy=50, rx=25, ry=25)
        assert circle.type == DrawingType.CIRCLE
        assert circle.cx == 50
        assert circle.cy == 50
        assert circle.rx == 25
        assert circle.ry == 25

    def test_ellipse(self):
        """Test ellipse with different radii"""
        ellipse = CircleDrawing(cx=0, cy=0, rx=30, ry=20)
        assert ellipse.rx != ellipse.ry

    def test_circle_bounds(self):
        """Test circle bounding box"""
        circle = CircleDrawing(cx=100, cy=100, rx=50, ry=30)
        bounds = circle.get_bounds()
        assert bounds == (50, 70, 150, 130)

    def test_circle_serialization(self):
        """Test circle serialization"""
        circle = CircleDrawing(
            id="circ1",
            cx=100,
            cy=100,
            rx=50,
            ry=50,
            style=DrawingStyle(fill_color="#0000FF"),
        )

        data = circle.to_dict()
        assert data["type"] == "circle"
        assert data["cx"] == 100
        assert data["rx"] == 50

        restored = CircleDrawing.from_dict(data)
        assert restored.cx == 100
        assert restored.style.fill_color == "#0000FF"


class TestRectDrawing:
    """Test RectDrawing class"""

    def test_create_rect(self):
        """Test creating a rectangle drawing"""
        rect = RectDrawing(x=10, y=20, width=100, height=50)
        assert rect.type == DrawingType.RECT
        assert rect.x == 10
        assert rect.y == 20
        assert rect.width == 100
        assert rect.height == 50

    def test_rect_corner_radius(self):
        """Test rectangle with rounded corners"""
        rect = RectDrawing(x=0, y=0, width=100, height=100, corner_radius=10)
        assert rect.corner_radius == 10

    def test_rect_bounds(self):
        """Test rectangle bounding box"""
        rect = RectDrawing(x=10, y=20, width=100, height=50)
        bounds = rect.get_bounds()
        assert bounds == (10, 20, 110, 70)

    def test_rect_serialization(self):
        """Test rectangle serialization"""
        rect = RectDrawing(
            id="rect1", x=0, y=0, width=200, height=100, corner_radius=15
        )

        data = rect.to_dict()
        assert data["type"] == "rect"
        assert data["width"] == 200
        assert data["corner_radius"] == 15

        restored = RectDrawing.from_dict(data)
        assert restored.width == 200
        assert restored.corner_radius == 15


class TestTextDrawing:
    """Test TextDrawing class"""

    def test_create_text(self):
        """Test creating a text drawing"""
        text = TextDrawing(
            x=100, y=100, text="Hello World", font_family="Arial", font_size=16
        )
        assert text.type == DrawingType.TEXT
        assert text.text == "Hello World"
        assert text.font_family == "Arial"
        assert text.font_size == 16

    def test_text_styling(self):
        """Test text styling options"""
        text = TextDrawing(
            x=0,
            y=0,
            text="Styled",
            bold=True,
            italic=True,
            text_color="#FF0000",
            alignment="center",
        )
        assert text.bold is True
        assert text.italic is True
        assert text.text_color == "#FF0000"
        assert text.alignment == "center"

    def test_text_serialization(self):
        """Test text serialization"""
        text = TextDrawing(
            id="text1", x=50, y=50, text="Test Text", font_size=24, bold=True
        )

        data = text.to_dict()
        assert data["type"] == "text"
        assert data["text"] == "Test Text"
        assert data["font_size"] == 24
        assert data["bold"] is True

        restored = TextDrawing.from_dict(data)
        assert restored.text == "Test Text"
        assert restored.font_size == 24


class TestSnapToAngle:
    """Test angle snapping function"""

    def test_snap_horizontal(self):
        """Test snapping to horizontal line"""
        x2, y2 = snap_to_angle(0, 0, 100, 5, 45.0)
        assert y2 == pytest.approx(0, abs=1)  # Should snap to 0 degrees

    def test_snap_vertical(self):
        """Test snapping to vertical line"""
        x2, y2 = snap_to_angle(0, 0, 5, 100, 45.0)
        assert x2 == pytest.approx(0, abs=1)  # Should snap to 90 degrees

    def test_snap_45_degree(self):
        """Test snapping to 45 degree line"""
        x2, y2 = snap_to_angle(0, 0, 100, 95, 45.0)
        # Should snap to 45 degrees - x2 and y2 should be equal
        assert abs(x2) == pytest.approx(abs(y2), rel=0.1)

    def test_snap_zero_length(self):
        """Test snapping with zero length line"""
        x2, y2 = snap_to_angle(50, 50, 50, 50, 45.0)
        assert x2 == 50
        assert y2 == 50


class TestDrawingManager:
    """Test DrawingManager class"""

    @pytest.fixture
    def mock_plot_widget(self):
        """Create a mock plot widget"""
        mock = MagicMock()
        mock.addItem = MagicMock()
        mock.removeItem = MagicMock()
        return mock

    def test_add_drawing(self, mock_plot_widget):
        """Test adding a drawing"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=100, y2=100)

        drawing_id = manager.add_drawing(line)

        assert drawing_id == line.id
        assert len(manager.get_all_drawings()) == 1
        mock_plot_widget.addItem.assert_called()

    def test_remove_drawing(self, mock_plot_widget):
        """Test removing a drawing"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        drawing_id = manager.add_drawing(line)

        result = manager.remove_drawing(drawing_id)

        assert result is True
        assert len(manager.get_all_drawings()) == 0
        mock_plot_widget.removeItem.assert_called()

    def test_remove_nonexistent(self, mock_plot_widget):
        """Test removing non-existent drawing"""
        manager = DrawingManager(mock_plot_widget)
        result = manager.remove_drawing("nonexistent")
        assert result is False

    def test_select_drawing(self, mock_plot_widget):
        """Test selecting a drawing"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        drawing_id = manager.add_drawing(line)

        manager.select_drawing(drawing_id)

        assert manager.get_selected_id() == drawing_id

    def test_delete_selected(self, mock_plot_widget):
        """Test deleting selected drawing"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        drawing_id = manager.add_drawing(line)
        manager.select_drawing(drawing_id)

        result = manager.delete_selected()

        assert result is True
        assert len(manager.get_all_drawings()) == 0
        assert manager.get_selected_id() is None

    def test_serialization(self, mock_plot_widget):
        """Test manager serialization"""
        manager = DrawingManager(mock_plot_widget)
        manager.add_drawing(LineDrawing(x1=0, y1=0, x2=100, y2=100))
        manager.add_drawing(CircleDrawing(cx=50, cy=50, rx=25, ry=25))

        data = manager.to_dict()

        assert "drawings" in data
        assert len(data["drawings"]) == 2

    def test_deserialization(self, mock_plot_widget):
        """Test manager deserialization"""
        manager = DrawingManager(mock_plot_widget)

        data = {
            "drawings": [
                {
                    "id": "line1",
                    "type": "line",
                    "x1": 0,
                    "y1": 0,
                    "x2": 100,
                    "y2": 100,
                    "visible": True,
                    "locked": False,
                    "z_order": 100,
                    "style": {
                        "stroke_color": "#000000",
                        "stroke_width": 2.0,
                        "line_style": "solid",
                        "fill_color": None,
                        "fill_opacity": 0.3,
                    },
                }
            ],
            "z_counter": 101,
        }

        manager.from_dict(data)

        assert len(manager.get_all_drawings()) == 1
        line = manager.get_drawing("line1")
        assert line is not None
        assert line.x1 == 0
        assert line.x2 == 100

    def test_clear(self, mock_plot_widget):
        """Test clearing all drawings"""
        manager = DrawingManager(mock_plot_widget)
        manager.add_drawing(LineDrawing(x1=0, y1=0, x2=100, y2=100))
        manager.add_drawing(CircleDrawing(cx=50, cy=50, rx=25, ry=25))

        manager.clear()

        assert len(manager.get_all_drawings()) == 0


class TestUndoRedo:
    """Test undo/redo functionality"""

    @pytest.fixture
    def mock_plot_widget(self):
        """Create a mock plot widget"""
        mock = MagicMock()
        mock.addItem = MagicMock()
        mock.removeItem = MagicMock()
        return mock

    def test_undo_add(self, mock_plot_widget):
        """Test undo after adding"""
        manager = DrawingManager(mock_plot_widget)
        manager.add_drawing(LineDrawing(x1=0, y1=0, x2=100, y2=100))

        result = manager.undo()

        assert result is True
        assert len(manager.get_all_drawings()) == 0

    def test_redo_after_undo(self, mock_plot_widget):
        """Test redo after undo"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        manager.add_drawing(line)
        manager.undo()

        result = manager.redo()

        assert result is True
        assert len(manager.get_all_drawings()) == 1

    def test_undo_empty(self, mock_plot_widget):
        """Test undo with no history"""
        manager = DrawingManager(mock_plot_widget)
        result = manager.undo()
        assert result is False

    def test_redo_empty(self, mock_plot_widget):
        """Test redo with no history"""
        manager = DrawingManager(mock_plot_widget)
        result = manager.redo()
        assert result is False

    def test_redo_cleared_on_new_action(self, mock_plot_widget):
        """Test that redo stack is cleared on new action"""
        manager = DrawingManager(mock_plot_widget)
        manager.add_drawing(LineDrawing(x1=0, y1=0, x2=100, y2=100))
        manager.undo()

        # New action should clear redo stack
        manager.add_drawing(CircleDrawing(cx=50, cy=50, rx=25, ry=25))

        result = manager.redo()
        assert result is False


class TestToolModeDrawing:
    """Test ToolMode enum has drawing modes"""

    def test_drawing_modes_exist(self):
        """Test that drawing modes are defined in ToolMode"""
        assert ToolMode.LINE_DRAW.value == "line_draw"
        assert ToolMode.CIRCLE_DRAW.value == "circle_draw"
        assert ToolMode.RECT_DRAW.value == "rect_draw"
        assert ToolMode.TEXT_DRAW.value == "text_draw"

    def test_all_tool_modes(self):
        """Test that all tool modes are accessible"""
        modes = [
            ToolMode.ZOOM,
            ToolMode.PAN,
            ToolMode.RECT_SELECT,
            ToolMode.LASSO_SELECT,
            ToolMode.LINE_DRAW,
            ToolMode.CIRCLE_DRAW,
            ToolMode.RECT_DRAW,
            ToolMode.TEXT_DRAW,
        ]
        assert len(modes) == 8


class TestHitTesting:
    """Test hit testing for drawing selection"""

    @pytest.fixture
    def mock_plot_widget(self):
        mock = MagicMock()
        mock.addItem = MagicMock()
        mock.removeItem = MagicMock()
        return mock

    def test_find_line_at_position(self, mock_plot_widget):
        """Test finding a line at a position"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        manager.add_drawing(line)

        # Point on the line
        found_id = manager.find_drawing_at(50, 50)
        assert found_id == line.id

    def test_find_nothing_at_empty_position(self, mock_plot_widget):
        """Test finding nothing at empty position"""
        manager = DrawingManager(mock_plot_widget)
        line = LineDrawing(x1=0, y1=0, x2=10, y2=10)
        manager.add_drawing(line)

        # Point far from the line
        found_id = manager.find_drawing_at(500, 500)
        assert found_id is None

    def test_find_topmost_overlapping(self, mock_plot_widget):
        """Test finding topmost drawing when overlapping"""
        manager = DrawingManager(mock_plot_widget)
        line1 = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        line2 = LineDrawing(x1=0, y1=0, x2=100, y2=100)
        manager.add_drawing(line1)
        manager.add_drawing(line2)

        # Should find the last added (topmost)
        found_id = manager.find_drawing_at(50, 50)
        assert found_id == line2.id
