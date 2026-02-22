"""
Drawing Tools Mixin for GraphPanel.

Extracted from graph_panel.py as part of the Phase 1 GOAT refactoring.
Uses the mixin pattern so that ``self`` still resolves to the GraphPanel
instance — avoiding the need to pass multiple dependencies through constructors.

Attributes accessed on ``self`` (from GraphPanel):
    _drawing_manager, main_graph
"""

from typing import Dict, Any

from PySide6.QtWidgets import QDialog

from ....ui.drawing import DrawingManager, DrawingStyle, DrawingStyleDialog


class DrawingToolsMixin:
    """Mixin providing drawing tool methods for GraphPanel."""

    def get_drawing_manager(self) -> DrawingManager:
        """Get the drawing manager."""
        return self._drawing_manager

    def set_drawing_style(self, style: DrawingStyle):
        """Set the current drawing style for new drawings."""
        self._drawing_manager.current_style = style
        self.main_graph.set_drawing_style(style)

    def set_drawing_color(self, color_hex: str):
        """Set the stroke color for new drawings."""
        self._drawing_manager.current_style.stroke_color = color_hex
        self.main_graph._current_drawing_style.stroke_color = color_hex

    def get_drawings_data(self) -> Dict[str, Any]:
        """Get all drawings as serializable dict (for saving)."""
        return self._drawing_manager.to_dict()

    def load_drawings_data(self, data: Dict[str, Any]):
        """Load drawings from serialized dict."""
        self._drawing_manager.from_dict(data)

    def clear_drawings(self):
        """Clear all drawings."""
        self._drawing_manager.clear()

    def undo_drawing(self) -> bool:
        """Undo last drawing action."""
        return self._drawing_manager.undo()

    def redo_drawing(self) -> bool:
        """Redo last undone action."""
        return self._drawing_manager.redo()

    def delete_selected_drawing(self) -> bool:
        """Delete the currently selected drawing."""
        return self._drawing_manager.delete_selected()

    def show_drawing_style_dialog(self):
        """Show dialog to configure drawing style."""
        dialog = DrawingStyleDialog("Drawing Style", self)
        dialog.set_style(self._drawing_manager.current_style)
        if dialog.exec() == QDialog.Accepted:
            style = dialog.get_style()
            self.set_drawing_style(style)
