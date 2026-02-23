"""
Stylesheet preservation tests — documents current generate_stylesheet() output
before the theme.py split refactor.

These tests must PASS against the unmodified theme.py. They act as a behavioral
contract: if the refactor changes what generate_stylesheet() produces, these fail.
"""

from data_graph_studio.ui.theme import ThemeManager


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
