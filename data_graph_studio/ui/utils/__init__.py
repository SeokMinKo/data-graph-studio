"""UI utilities — shared helpers for theme detection, icon mapping, etc."""

from __future__ import annotations

from typing import Any


def is_light_theme(window_or_theme_manager: Any) -> bool:
    """Determine whether the current theme is light.

    Accepts either a MainWindow (with ``_theme_manager``) or a ThemeManager
    directly.  Returns *False* on any failure so callers never need
    ``try / except`` or deeply nested ``getattr`` chains.

    Issue #17 — replaces 4× duplicated one-liner in dataset_controller.
    """
    tm = window_or_theme_manager
    # If we got a MainWindow, drill into _theme_manager
    if hasattr(tm, "_theme_manager"):
        tm = getattr(tm, "_theme_manager", None)
    if tm is None:
        return False
    ct = getattr(tm, "current_theme", None)
    if ct is None:
        return False
    try:
        return bool(ct.is_light())
    except Exception:
        return False


# ---- Chart-type → emoji icon mapping (Issue #14) ----

_CHART_TYPE_ICONS: dict[str, str] = {
    "line": "📈",
    "bar": "📊",
    "scatter": "⚬",
    "area": "▤",
    "pie": "🥧",
    "histogram": "▦",
    "box": "📦",
    "violin": "🎻",
    "heatmap": "🗺️",
    "radar": "🕸️",
    "treemap": "🌳",
    "funnel": "🔽",
    "waterfall": "💧",
    "candlestick": "🕯️",
    "donut": "🍩",
    "bubble": "🫧",
}


def chart_type_icon(chart_type: str) -> str:
    """Return an emoji icon for the given *chart_type* string.

    Issue #14 — extracted from ProfileModel so presentation logic
    doesn't live inside the data model.
    """
    return _CHART_TYPE_ICONS.get((chart_type or "").lower(), "📊")
