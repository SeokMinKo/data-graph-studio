"""Base (shared) stylesheet — applies to both light and dark themes.

Coordinator: combines Qt built-in widget styles (widget_stylesheet) with
app-specific panel styles (panel_stylesheet).
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .theme import Theme


def base_stylesheet(t: "Theme") -> str:
    """Return the complete application stylesheet by combining all sections.

    Args:
        t: Current Theme instance.

    Returns:
        Full QSS string for the application.
    """
    from ._theme_stylesheet_widgets import widget_stylesheet
    from ._theme_stylesheet_panels import panel_stylesheet
    return widget_stylesheet(t) + panel_stylesheet(t)
