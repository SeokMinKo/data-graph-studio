import re
from pathlib import Path

from data_graph_studio.ui.theme import ThemeManager
from data_graph_studio.ui.panels.color_scheme import ColorSchemeManager


def test_theme_text_contrast_tokens_updated():
    tm = ThemeManager()

    light = tm._themes["light"]
    assert light.text_muted.lower() == "#6b7280"
    assert light.text_disabled.lower() == "#9ca3af"

    dark = tm._themes["dark"]
    assert dark.text_muted.lower() == "#9ca3af"

    midnight = tm._themes["midnight"]
    assert midnight.text_muted.lower() == "#9ca3af"


def test_high_contrast_theme_exists():
    tm = ThemeManager()
    assert "high-contrast" in tm.list_themes()


def test_minimum_font_size_in_theme_stylesheet_is_11px():
    tm = ThemeManager()
    css = tm.generate_stylesheet()
    sizes = [int(m.group(1)) for m in re.finditer(r"font-size:\s*(\d+)px", css)]
    assert sizes, "No font-size declarations found"
    assert min(sizes) >= 11


def test_colorblind_safe_palettes_exist():
    csm = ColorSchemeManager()
    assert csm.get_scheme("Colorblind Safe") is not None
    assert csm.get_scheme("RYB") is not None


def test_click_target_sizes_updated_in_source():
    src = Path("data_graph_studio/ui/panels/table_panel.py").read_text(encoding="utf-8")
    assert "setFixedSize(24, 24)" in src

    drawing_src = Path("data_graph_studio/ui/drawing.py").read_text(encoding="utf-8")
    assert "setFixedSize(32, 32)" in drawing_src


def test_accessible_name_patterns_present_in_key_files():
    files = [
        Path("data_graph_studio/ui/main_window.py"),
        Path("data_graph_studio/ui/panels/table_panel.py"),
        Path("data_graph_studio/ui/panels/graph_panel.py"),
        Path("data_graph_studio/ui/panels/stat_panel.py"),
        Path("data_graph_studio/ui/panels/profile_bar.py"),
    ]
    for f in files:
        text = f.read_text(encoding="utf-8")
        assert "setAccessibleName(" in text, f"No accessible name assignment found in {f}"
