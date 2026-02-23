"""
Stylesheet preservation tests — documents current generate_stylesheet() output
before the theme.py split refactor.

These tests must PASS against the unmodified theme.py. They act as a behavioral
contract: if the refactor changes what generate_stylesheet() produces, these fail.
"""

import pytest

from data_graph_studio.ui.theme import ThemeManager

# Selectors sampled at ~35-line intervals across the 282 selector lines in the
# dark stylesheet — each comes from a different logical section of the file.
EXPECTED_SELECTORS = [
    "QScrollBar::handle:vertical:hover",  # scrollbar section
    "QTabWidget::pane",                   # tab widget section
    "#XAxisZone",                         # graph axis zone
    "#graphPlaceholder",                  # graph placeholder
    "#settingIcon",                       # settings icon
    "#guideText",                         # guide/help text
    "#generateBtn:hover",                 # generate button states
    "#placeholder",                       # generic placeholder
]

# Top dark-mode background colors — verified absent from light output.
DARK_MODE_COLORS = ("#1E293B", "#334155", "#374151")

# Qt widget class names that must appear in any valid Qt stylesheet.
EXPECTED_QT_MARKERS = ("QMainWindow", "QWidget")


@pytest.fixture
def dark_mgr():
    mgr = ThemeManager()
    mgr.set_theme("dark")
    return mgr


@pytest.fixture
def light_mgr():
    mgr = ThemeManager()
    mgr.set_theme("light")
    return mgr


class TestGenerateStylesheetPreservation:
    """Verify generate_stylesheet() output shape for both light and dark modes."""

    def test_light_stylesheet_is_non_empty_string(self, light_mgr):
        result = light_mgr.generate_stylesheet()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_dark_stylesheet_is_non_empty_string(self, dark_mgr):
        result = dark_mgr.generate_stylesheet()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_stylesheet_contains_qt_markers(self, dark_mgr):
        """Output must reference known Qt widget classes — confirms it's a real Qt stylesheet."""
        result = dark_mgr.generate_stylesheet()
        for marker in EXPECTED_QT_MARKERS:
            assert marker in result

    def test_light_and_dark_stylesheets_differ(self, light_mgr, dark_mgr):
        """Light and dark themes must produce distinct output."""
        assert light_mgr.generate_stylesheet() != dark_mgr.generate_stylesheet()

    def test_stylesheet_is_deterministic(self, dark_mgr):
        """Calling generate_stylesheet() twice with the same theme yields the same result."""
        assert dark_mgr.generate_stylesheet() == dark_mgr.generate_stylesheet()

    def test_stylesheet_minimum_length(self, dark_mgr):
        """Stylesheet must meet a minimum character count — a dropped sub-file would shrink it noticeably."""
        css = dark_mgr.generate_stylesheet()
        assert len(css) > 40_000, (
            f"Stylesheet too short ({len(css)} chars) — a sub-file may have been dropped"
        )

    def test_stylesheet_covers_key_sections(self, dark_mgr):
        """Spot-check selectors sampled from across the file to catch silent section drops."""
        css = dark_mgr.generate_stylesheet()
        for sel in EXPECTED_SELECTORS:
            assert sel in css, f"Missing section: {sel}"

    def test_dark_stylesheet_contains_dark_colors(self, dark_mgr):
        """Dark mode stylesheet must include dark background colors."""
        dark_css = dark_mgr.generate_stylesheet()
        for color in DARK_MODE_COLORS:
            assert color in dark_css, f"Dark color {color} missing from dark stylesheet"

    def test_dark_colors_absent_from_light_stylesheet(self, light_mgr):
        """Dark mode background colors must not appear in light mode output."""
        light_css = light_mgr.generate_stylesheet()
        for color in DARK_MODE_COLORS:
            assert color not in light_css, f"Dark color {color} unexpectedly found in light stylesheet"
