"""
Stylesheet preservation tests — documents current generate_stylesheet() output
before the theme.py split refactor.

These tests must PASS against the unmodified theme.py. They act as a behavioral
contract: if the refactor changes what generate_stylesheet() produces, these fail.
"""

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


class TestGenerateStylesheetPreservation:
    """Verify generate_stylesheet() output shape for both light and dark modes."""

    def test_light_stylesheet_is_non_empty_string(self):
        mgr = ThemeManager()
        mgr.set_theme("light")
        result = mgr.generate_stylesheet()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_dark_stylesheet_is_non_empty_string(self):
        mgr = ThemeManager()
        mgr.set_theme("dark")
        result = mgr.generate_stylesheet()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_stylesheet_contains_qt_markers(self):
        """Output must reference known Qt widget classes — confirms it's a real Qt stylesheet."""
        mgr = ThemeManager()
        mgr.set_theme("dark")
        result = mgr.generate_stylesheet()
        # Qt stylesheet identifiers that must be present
        assert "QMainWindow" in result
        assert "QWidget" in result

    def test_light_and_dark_stylesheets_differ(self):
        """Light and dark themes must produce distinct output."""
        mgr = ThemeManager()

        mgr.set_theme("light")
        light_css = mgr.generate_stylesheet()

        mgr.set_theme("dark")
        dark_css = mgr.generate_stylesheet()

        assert light_css != dark_css

    def test_stylesheet_is_deterministic(self):
        """Calling generate_stylesheet() twice with the same theme yields the same result."""
        mgr = ThemeManager()
        mgr.set_theme("dark")
        assert mgr.generate_stylesheet() == mgr.generate_stylesheet()

    def test_stylesheet_minimum_length(self):
        """Stylesheet must meet a minimum character count — a dropped sub-file would shrink it noticeably."""
        mgr = ThemeManager()
        mgr.set_theme("dark")
        css = mgr.generate_stylesheet()
        assert len(css) > 40_000, (
            f"Stylesheet too short ({len(css)} chars) — a sub-file may have been dropped"
        )

    def test_stylesheet_covers_key_sections(self):
        """Spot-check selectors sampled from across the file to catch silent section drops."""
        mgr = ThemeManager()
        mgr.set_theme("dark")
        css = mgr.generate_stylesheet()
        for sel in EXPECTED_SELECTORS:
            assert sel in css, f"Missing section: {sel}"

    def test_dark_stylesheet_contains_dark_colors(self):
        """Dark mode must include dark background colors that are absent from light mode."""
        mgr = ThemeManager()

        mgr.set_theme("dark")
        dark_css = mgr.generate_stylesheet()

        mgr.set_theme("light")
        light_css = mgr.generate_stylesheet()

        # Top dark-mode colors (#1E293B, #334155, #374151) verified absent from light output
        for color in ("#1E293B", "#334155", "#374151"):
            assert color in dark_css, f"Dark color {color} missing from dark stylesheet"
            assert color not in light_css, f"Dark color {color} unexpectedly found in light stylesheet"
