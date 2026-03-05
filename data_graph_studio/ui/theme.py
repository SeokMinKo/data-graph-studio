"""
Theme - Modern Light/Dark Mode with Glassmorphism and Soft UI
"""

from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


@dataclass
class Theme:
    """Modern Theme with glassmorphism support"""
    name: str
    background: str
    foreground: str
    primary: str
    secondary: str
    
    # Accent Colors (Vibrant)
    accent: str = "#59B8E3"       # Indigo
    success: str = "#10B981"      # Emerald
    warning: str = "#F59E0B"      # Amber
    error: str = "#EF4444"        # Red
    info: str = "#3B82F6"         # Blue
    
    # Surface Colors (Cards, Panels)
    surface: str = ""
    surface_hover: str = ""
    surface_active: str = ""
    
    # Border & Dividers
    border: str = ""
    border_light: str = ""
    
    # Interactive States
    hover: str = ""
    selected: str = ""
    focused: str = ""
    
    # Text Hierarchy
    text_primary: str = ""
    text_secondary: str = ""
    text_muted: str = ""
    text_disabled: str = ""
    
    # Shadows (for glassmorphism)
    shadow_color: str = ""
    
    # Gradients
    gradient_start: str = ""
    gradient_end: str = ""
    
    def __post_init__(self):
        is_light = self.is_light()
        
        # Surface colors (light: bright, dark: dark)
        if not self.surface:
            self.surface = "#FFFFFF" if is_light else "#1F2937"
        if not self.surface_hover:
            self.surface_hover = "#F9FAFB" if is_light else "#374151"
        if not self.surface_active:
            self.surface_active = "#F3F4F6" if is_light else "#4B5563"
        
        # Borders (light: light gray, dark: dark gray)
        if not self.border:
            self.border = "#E5E7EB" if is_light else "#374151"
        if not self.border_light:
            self.border_light = "#F3F4F6" if is_light else "#1F2937"
        
        # Interactive (light: light hover, dark: dark hover)
        if not self.hover:
            self.hover = "#F3F4F6" if is_light else "#374151"
        if not self.selected:
            self.selected = "#EFF6FF" if is_light else (self.primary + "20")
        if not self.focused:
            self.focused = self.primary + "30"
        
        # Text (light: dark text, dark: light text)
        if not self.text_primary:
            self.text_primary = self.foreground
        if not self.text_secondary:
            self.text_secondary = "#6B7280" if is_light else "#9CA3AF"
        if not self.text_muted:
            self.text_muted = "#6B7280" if is_light else "#9CA3AF"  # WCAG AA ~4.6:1
        if not self.text_disabled:
            self.text_disabled = "#9CA3AF" if is_light else "#6B7280"  # improved for disabled
        
        # Shadow (light: subtle, dark: stronger)
        if not self.shadow_color:
            self.shadow_color = "rgba(0, 0, 0, 0.08)" if is_light else "rgba(0, 0, 0, 0.25)"
        
        # Gradient
        if not self.gradient_start:
            self.gradient_start = self.primary
        if not self.gradient_end:
            self.gradient_end = self.accent
    
    def is_light(self) -> bool:
        """라이트 테마 여부"""
        bg = self.background.lstrip('#')
        if len(bg) == 6:
            r, g, b = int(bg[0:2], 16), int(bg[2:4], 16), int(bg[4:6], 16)
            luminance = (0.299 * r + 0.587 * g + 0.114 * b)
            return luminance > 128
        return True
    
    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {k: v for k, v in self.__dict__.items()}
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Theme':
        """딕셔너리에서 복원"""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class ColorPalette:
    """Modern Chart Color Palette"""
    
    def __init__(self, colors: List[str]):
        self.colors = colors
    
    def get(self, index: int) -> str:
        return self.colors[index % len(self.colors)]
    
    def __len__(self) -> int:
        return len(self.colors)
    
    def __iter__(self):
        return iter(self.colors)
    
    @classmethod
    def default(cls) -> 'ColorPalette':
        """Modern vibrant palette"""
        return cls([
            "#59B8E3",  # Indigo
            "#EC4899",  # Pink
            "#10B981",  # Emerald
            "#F59E0B",  # Amber
            "#3B82F6",  # Blue
            "#EF4444",  # Red
            "#8B5CF6",  # Violet
            "#06B6D4",  # Cyan
            "#84CC16",  # Lime
            "#F97316",  # Orange
        ])
    
    @classmethod
    def ocean(cls) -> 'ColorPalette':
        """Ocean blue palette"""
        return cls([
            "#0EA5E9",  # Sky
            "#06B6D4",  # Cyan
            "#14B8A6",  # Teal
            "#3B82F6",  # Blue
            "#59B8E3",  # Indigo
            "#8B5CF6",  # Violet
            "#0284C7",  # Light Blue
            "#0891B2",  # Cyan Dark
            "#0D9488",  # Teal Dark
            "#2563EB",  # Blue Dark
        ])
    
    @classmethod
    def sunset(cls) -> 'ColorPalette':
        """Warm sunset palette"""
        return cls([
            "#F97316",  # Orange
            "#EF4444",  # Red
            "#EC4899",  # Pink
            "#F59E0B",  # Amber
            "#FBBF24",  # Yellow
            "#DC2626",  # Red Dark
            "#DB2777",  # Pink Dark
            "#D97706",  # Amber Dark
            "#EA580C",  # Orange Dark
            "#F43F5E",  # Rose
        ])
    
    @classmethod
    def forest(cls) -> 'ColorPalette':
        """Natural green palette"""
        return cls([
            "#10B981",  # Emerald
            "#22C55E",  # Green
            "#84CC16",  # Lime
            "#14B8A6",  # Teal
            "#059669",  # Emerald Dark
            "#16A34A",  # Green Dark
            "#65A30D",  # Lime Dark
            "#0D9488",  # Teal Dark
            "#047857",  # Emerald Darker
            "#15803D",  # Green Darker
        ])


# ==================== Built-in Themes ====================

# Light Theme - OpenAI Codex Style
LIGHT_THEME = Theme(
    name="Light",
    background="#FFFFFF",
    foreground="#111827",
    primary="#3B82F6",
    secondary="#8B5CF6",
    surface="#FFFFFF",
    surface_hover="#F9FAFB",
    surface_active="#F3F4F6",
    border="#E5E7EB",
    border_light="#F3F4F6",
    hover="#F3F4F6",
    selected="#EFF6FF",
    text_primary="#111827",
    text_secondary="#6B7280",
    text_muted="#6B7280",       # WCAG AA ~4.6:1 on white
    text_disabled="#9CA3AF",    # improved disabled contrast
    accent="#8B5CF6",
)

# Dark Theme - Sleek & Modern
DARK_THEME = Theme(
    name="Dark",
    background="#0F172A",
    foreground="#F1F5F9",
    primary="#818CF8",
    secondary="#F472B6",
    surface="#1E293B",
    border="#334155",
    accent="#A78BFA",
)

# Midnight Blue Theme
MIDNIGHT_THEME = Theme(
    name="Midnight",
    background="#0B1120",
    foreground="#E2E8F0",
    primary="#38BDF8",
    secondary="#FB7185",
    surface="#1E293B",
    border="#1E3A5F",
    accent="#22D3EE",
)

# Tailwind CSS Theme — Slate + Indigo, clean utility-first aesthetic
TAILWIND_THEME = Theme(
    name="Tailwind",
    background="#F8FAFC",        # slate-50
    foreground="#0F172A",        # slate-900
    primary="#6366F1",           # indigo-500
    secondary="#EC4899",         # pink-500
    accent="#8B5CF6",            # violet-500
    success="#22C55E",           # green-500
    warning="#F59E0B",           # amber-500
    error="#EF4444",             # red-500
    info="#06B6D4",              # cyan-500
    surface="#FFFFFF",           # white
    surface_hover="#F1F5F9",     # slate-100
    surface_active="#E2E8F0",    # slate-200
    border="#CBD5E1",            # slate-300
    border_light="#E2E8F0",      # slate-200
    hover="#EEF2FF",             # indigo-50
    selected="#E0E7FF",          # indigo-100
    focused="#6366F140",         # indigo-500/25
    text_primary="#0F172A",      # slate-900
    text_secondary="#475569",    # slate-600
    text_muted="#64748B",        # slate-500 (WCAG AA ~5.5:1)
    text_disabled="#94A3B8",     # slate-400 (improved)
    shadow_color="rgba(15, 23, 42, 0.06)",  # slate-900/6
    gradient_start="#6366F1",    # indigo-500
    gradient_end="#8B5CF6",      # violet-500
)

# Tailwind Dark Theme — Slate dark + Indigo accents
TAILWIND_DARK_THEME = Theme(
    name="Tailwind Dark",
    background="#020617",        # slate-950
    foreground="#F8FAFC",        # slate-50
    primary="#818CF8",           # indigo-400
    secondary="#F472B6",         # pink-400
    accent="#A78BFA",            # violet-400
    success="#4ADE80",           # green-400
    warning="#FBBF24",           # amber-400
    error="#F87171",             # red-400
    info="#22D3EE",              # cyan-400
    surface="#0F172A",           # slate-900
    surface_hover="#1E293B",     # slate-800
    surface_active="#334155",    # slate-700
    border="#334155",            # slate-700
    border_light="#1E293B",      # slate-800
    hover="#1E1B4B",             # indigo-950
    selected="#312E81",          # indigo-900
    focused="#818CF840",         # indigo-400/25
    text_primary="#F8FAFC",      # slate-50
    text_secondary="#94A3B8",    # slate-400
    text_muted="#94A3B8",        # slate-400 (WCAG AA ~4.6:1 on dark)
    text_disabled="#64748B",     # slate-500 (improved)
    shadow_color="rgba(0, 0, 0, 0.30)",
    gradient_start="#818CF8",    # indigo-400
    gradient_end="#A78BFA",      # violet-400
)


# High Contrast Theme — WCAG AAA 7:1 contrast ratio
HIGH_CONTRAST_THEME = Theme(
    name="High Contrast",
    background="#000000",
    foreground="#FFFFFF",
    primary="#00FFFF",           # Cyan
    secondary="#FF00FF",         # Magenta
    accent="#FFFF00",            # Yellow
    success="#00FF00",           # Green
    warning="#FFFF00",           # Yellow
    error="#FF0000",             # Red
    info="#00FFFF",              # Cyan
    surface="#1A1A1A",
    surface_hover="#333333",
    surface_active="#4D4D4D",
    border="#FFFFFF",
    border_light="#CCCCCC",
    hover="#333333",
    selected="#003366",
    focused="#00FFFF40",
    text_primary="#FFFFFF",
    text_secondary="#E0E0E0",
    text_muted="#C0C0C0",
    text_disabled="#808080",
    shadow_color="rgba(0, 0, 0, 0.5)",
    gradient_start="#00FFFF",
    gradient_end="#FFFF00",
)


class ThemeManager:
    """Modern Theme Manager with animations support"""
    
    BUILTIN_THEMES = {'light', 'dark', 'midnight', 'tailwind', 'tailwind-dark', 'high-contrast'}
    
    def __init__(self):
        self._themes: Dict[str, Theme] = {
            'light': LIGHT_THEME,
            'dark': DARK_THEME,
            'midnight': MIDNIGHT_THEME,
            'tailwind': TAILWIND_THEME,
            'tailwind-dark': TAILWIND_DARK_THEME,
            'high-contrast': HIGH_CONTRAST_THEME,
        }
        self._current: str = 'midnight'
        self._chart_palette: ColorPalette = ColorPalette.default()
        self._theme_preference: str = 'system'  # PRD §3.6: "light" | "dark" | "system"
    
    @property
    def current_theme(self) -> Theme:
        return self._themes[self._current]
    
    def list_themes(self) -> List[str]:
        return list(self._themes.keys())
    
    def set_theme(self, theme_id: str):
        if theme_id in self._themes:
            self._current = theme_id
    
    def toggle(self):
        """
        FR-6.2: light ↔ dark 토글.

        동작:
        - preference가 'light' → 'dark' 전환
        - preference가 'dark' → 'light' 전환
        - preference가 'system' → resolve 결과의 반대로 전환
        - _current도 light↔dark 토글 (하위 호환)
        """
        if self._theme_preference == "light":
            self.set_theme_preference("dark")
        elif self._theme_preference == "dark":
            self.set_theme_preference("light")
        else:
            # system → resolve 결과의 반대
            resolved = self.resolve_theme()
            if resolved.is_light():
                self.set_theme_preference("dark")
            else:
                self.set_theme_preference("light")

        # 하위 호환: _current도 light↔dark 전환 (기존 테스트 지원)
        current_theme = self._themes.get(self._current)
        if current_theme:
            if current_theme.is_light():
                self._current = 'dark'
            else:
                self._current = 'light'
    
    def add_theme(self, theme_id: str, theme: Theme):
        self._themes[theme_id] = theme
    
    def remove_theme(self, theme_id: str) -> bool:
        if theme_id in self.BUILTIN_THEMES:
            return False
        if theme_id in self._themes:
            del self._themes[theme_id]
            if self._current == theme_id:
                self._current = 'light'
            return True
        return False
    
    def get_chart_palette(self) -> ColorPalette:
        return self._chart_palette
    
    def set_chart_palette(self, palette: ColorPalette):
        self._chart_palette = palette
    
    def generate_stylesheet(self) -> str:
        """Generate modern Qt stylesheet with soft UI"""
        t = self.current_theme
        
        return f"""
            /* ============ Global Reset ============ */
            * {{
                /* Cross-platform + CJK-safe default stack */
                font-family: 'Segoe UI', 'Malgun Gothic', 'Apple SD Gothic Neo', 'Noto Sans CJK KR', 'Noto Sans', 'Helvetica Neue', 'Arial', sans-serif;
                font-size: 13px;
            }}
            
            /* ============ Focus Ring (Accessibility) ============ */
            QWidget:focus {{
                outline: 2px solid {t.primary};
                outline-offset: 1px;
            }}
            
            QPushButton:focus, QToolButton:focus, QComboBox:focus,
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
            QCheckBox:focus, QListWidget:focus, QTableView:focus,
            QTreeView:focus {{
                border: 2px solid {t.primary};
            }}
            
            /* ============ Main Window ============ */
            QMainWindow {{
                background: {t.background};
            }}
            
            QWidget {{
                background-color: transparent;
                color: {t.foreground};
            }}
            
            /* ============ Cards & Surfaces ============ */
            QFrame {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-radius: 8px;
            }}
            
            QFrame[frameShape="4"] {{  /* StyledPanel */
                background-color: {t.surface};
                border: {"1px solid #D1D5DB" if t.is_light() else "none"};
                border-radius: 8px;
                padding: 4px;
            }}
            
            /* ============ Labels ============ */
            QLabel {{
                color: {t.foreground};
                background: transparent;
                border: none;
                padding: 2px;
            }}
            
            QLabel[class="title"] {{
                font-size: 16px;
                font-weight: 600;
                color: {t.foreground};
            }}
            
            QLabel[class="subtitle"] {{
                font-size: 12px;
                color: {t.text_secondary};
            }}
            
            QLabel[class="stat-value"] {{
                font-size: 24px;
                font-weight: 700;
                color: {t.primary};
            }}
            
            /* ============ Modern Buttons ============ */
            QPushButton {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
                min-height: 20px;
            }}
            
            QPushButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            QPushButton:pressed {{
                background-color: {t.surface_active};
            }}
            
            QPushButton:focus {{
                border: 2px solid {t.primary};
                outline: none;
            }}
            
            QPushButton[class="primary"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                color: white;
                border: none;
                font-weight: 600;
            }}
            
            QPushButton[class="primary"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.accent}, stop:1 {t.primary});
            }}
            
            QPushButton[class="danger"] {{
                background-color: {t.error};
                color: white;
                border: none;
            }}
            
            QPushButton[class="icon"] {{
                background-color: transparent;
                border: none;
                padding: 6px;
                border-radius: 6px;
            }}
            
            QPushButton[class="icon"]:hover {{
                background-color: {t.hover};
            }}
            
            /* ============ Input Fields ============ */
            QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                selection-background-color: {t.primary};
                selection-color: white;
                placeholder-text-color: {t.text_secondary};
            }}
            
            QLineEdit:hover, QTextEdit:hover {{
                border-color: {t.text_secondary};
            }}
            
            QLineEdit:focus, QTextEdit:focus {{
                border: 2px solid {t.primary};
                background-color: {t.surface};
            }}
            
            QLineEdit[class="search"] {{
                border-radius: 20px;
                padding-left: 16px;
            }}
            
            /* ============ Combo Box ============ */
            QComboBox {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                min-height: 20px;
                placeholder-text-color: {t.text_secondary};
            }}
            
            QComboBox:hover {{
                border-color: {t.primary};
            }}
            
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {t.text_secondary};
                margin-right: 8px;
            }}
            
            QComboBox QAbstractItemView {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
                selection-background-color: {t.primary};
                selection-color: white;
            }}
            
            /* ============ Modern Table ============ */
            QTableView {{
                background-color: {t.surface};
                color: {t.foreground};
                border: none;
                border-radius: 8px;
                gridline-color: {t.border_light};
                selection-background-color: {t.selected};
                alternate-background-color: {t.surface_hover};
            }}
            
            QTableView::item {{
                padding: 6px 10px;
                border: none;
            }}
            
            QTableView::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            QTableView::item:hover {{
                background-color: {t.hover};
            }}
            
            QHeaderView::section {{
                background-color: {t.surface};
                color: {t.text_secondary};
                border: none;
                border-bottom: 1px solid {t.border_light};
                padding: 8px 10px;
                font-weight: 600;
                font-size: 11px;
            }}
            
            QHeaderView::section:hover {{
                background-color: {t.surface_hover};
                color: {t.foreground};
            }}
            
            /* ============ Scroll Bars ============ */
            QScrollBar:vertical {{
                background-color: transparent;
                width: 10px;
                margin: 4px;
            }}
            
            QScrollBar::handle:vertical {{
                background-color: {t.text_muted};
                border-radius: 5px;
                min-height: 30px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background-color: {t.primary};
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 10px;
                margin: 4px;
            }}
            
            QScrollBar::handle:horizontal {{
                background-color: {t.text_muted};
                border-radius: 5px;
                min-width: 30px;
            }}
            
            QScrollBar::handle:horizontal:hover {{
                background-color: {t.primary};
            }}
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            
            /* ============ Splitter ============ */
            QSplitter::handle {{
                background-color: transparent;
            }}
            
            QSplitter::handle:hover {{
                background-color: {t.primary}80;
            }}
            
            QSplitter::handle:vertical {{
                height: 6px;
            }}
            
            QSplitter::handle:horizontal {{
                width: 6px;
            }}
            
            /* ============ Menu Bar ============ */
            QMenuBar {{
                background-color: {t.surface};
                color: {t.foreground};
                border-bottom: 1px solid {t.border};
                padding: 4px 8px;
            }}
            
            QMenuBar::item {{
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px;
            }}
            
            QMenuBar::item:selected {{
                background-color: {t.hover};
            }}
            
            QMenu {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 4px;
            }}
            
            QMenu::item {{
                padding: 10px 24px 10px 16px;
                border-radius: 6px;
                margin: 2px 4px;
            }}
            
            QMenu::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            QMenu::separator {{
                height: 1px;
                background-color: {t.border};
                margin: 8px 12px;
            }}
            
            /* ============ Tool Bar ============ */
            QToolBar {{
                background-color: {t.surface};
                border: none;
                border-bottom: 1px solid {t.border};
                padding: 8px 16px;
                spacing: 8px;
            }}
            
            QToolBar::separator {{
                width: 1px;
                background-color: {t.border};
                margin: 4px 8px;
            }}
            
            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
            }}
            
            QToolButton:hover {{
                background-color: {t.hover};
            }}
            
            QToolButton:checked {{
                background-color: {t.selected};
                color: {t.primary};
            }}
            
            /* ============ Status Bar ============ */
            QStatusBar {{
                background-color: {t.surface};
                color: {t.text_secondary};
                border-top: 1px solid {t.border};
                padding: 8px 16px;
                font-size: 12px;
            }}
            
            /* ============ Group Box ============ */
            QGroupBox {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                margin-top: 12px;
                padding: 8px;
                font-weight: 500;
            }}
            
            QGroupBox::title {{
                color: {t.text_secondary};
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                font-size: 11px;
                font-weight: 600;
            }}
            
            /* ============ Check Box ============ */
            QCheckBox {{
                spacing: 8px;
                color: {t.foreground};
            }}
            
            QCheckBox:checked {{
                color: {t.foreground};
                font-weight: 600;
            }}
            
            QCheckBox:unchecked {{
                color: {t.text_muted};
            }}
            
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {t.border};
                border-radius: 4px;
                background-color: {t.surface};
            }}
            
            QCheckBox::indicator:hover {{
                border-color: {t.primary};
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {t.primary};
                border-color: {t.primary};
            }}
            
            /* ============ List Widget ============ */
            QListWidget {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
            }}
            
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px;
            }}
            
            QListWidget::item:hover {{
                background-color: {t.hover};
            }}
            
            QListWidget::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            /* ============ Tab Widget ============ */
            QTabWidget::pane {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                margin-top: -1px;
            }}
            
            QTabBar::tab {{
                background-color: transparent;
                color: {t.text_secondary};
                padding: 10px 20px;
                margin-right: 4px;
                border-bottom: 2px solid transparent;
            }}
            
            QTabBar::tab:hover {{
                color: {t.foreground};
            }}
            
            QTabBar::tab:selected {{
                color: {t.primary};
                border-bottom: 2px solid {t.primary};
            }}
            
            /* ============ Wizard ============ */
            QWizard {{
                background-color: {t.background};
            }}
            
            QWizard > QWidget {{
                background-color: {t.background};
            }}
            
            QWizard QLabel#qt_wizard_title {{
                background-color: {"#F3F4F6" if t.is_light() else t.surface};
                color: {t.foreground};
                font-size: 16px;
                font-weight: 600;
                padding: 16px 24px;
                border-bottom: {"1px solid #E5E7EB" if t.is_light() else f"1px solid {t.border}"};
            }}
            
            QWizard QLabel#qt_wizard_subtitle {{
                background-color: {"#F3F4F6" if t.is_light() else t.surface};
                color: {t.text_secondary};
                padding: 8px 24px 16px 24px;
            }}
            
            QWizard QWidget#qt_wizard_header {{
                background-color: {"#F3F4F6" if t.is_light() else t.surface};
                border-bottom: {"1px solid #E5E7EB" if t.is_light() else f"1px solid {t.border}"};
            }}
            
            /* ============ Tooltips ============ */
            QToolTip {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            
            /* ============ Progress Bar ============ */
            QProgressBar {{
                background-color: {t.surface_hover};
                border: none;
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }}
            
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                border-radius: 4px;
            }}
            
            /* ============ Slider ============ */
            QSlider::groove:horizontal {{
                background-color: {t.surface_hover};
                height: 6px;
                border-radius: 3px;
            }}
            
            QSlider::handle:horizontal {{
                background-color: {t.primary};
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            
            QSlider::handle:horizontal:hover {{
                background-color: {t.accent};
            }}
            
            /* ============ Panel Backgrounds ============ */
            #GraphOptionsPanel {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-right: 1px solid {t.border};
                border-radius: 8px;
            }}

            #GraphOptionsPanel QTabBar::tab {{
                padding: 6px 10px;
                margin-right: 2px;
                min-width: 52px;
            }}
            
            #LegendPanel {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-radius: 8px;
            }}
            
            #StatPanel {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-left: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            /* ============ Section Headers ============ */
            #sectionHeader {{
                font-weight: 600;
                font-size: 13px;
                color: {t.foreground};
                padding: 4px;
                background: transparent;
            }}
            
            /* ============ Hint & Stats Labels ============ */
            #hintLabel {{
                font-size: 11px;
                color: {t.text_muted};
                font-style: italic;
                background: transparent;
            }}
            
            #statsLabel {{
                font-size: 12px;
                color: {t.text_secondary};
                background: transparent;
            }}
            
            #seriesNameLabel {{
                font-size: 11px;
                color: {t.foreground};
                background: transparent;
            }}
            
            /* ============ Small Buttons ============ */
            #smallButton {{
                font-size: 11px;
                padding: 4px 8px;
            }}
            
            /* ============ Stat Cards ============ */
            #StatCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #StatCard:hover {{
                background-color: {t.surface_hover};
            }}
            
            #cardIcon {{
                font-size: 12px;
                background: transparent;
            }}
            
            #cardTitle {{
                color: {t.text_secondary};
                font-size: 11px;
                font-weight: 500;
                background: transparent;
                border: none;
            }}
            
            #cardValue {{
                color: {t.foreground};
                font-size: 18px;
                font-weight: 600;
                background: transparent;
                border: none;
            }}
            
            #cardSubtitle {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
                border: none;
            }}
            
            #cardSubtitle[trend="positive"] {{
                color: {t.success};
                font-weight: 500;
            }}
            
            #cardSubtitle[trend="negative"] {{
                color: {t.error};
                font-weight: 500;
            }}
            
            #cardSubtitle[trend="neutral"] {{
                color: {t.text_muted};
            }}
            
            /* ============ Context Label ============ */
            #contextLabel {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
                padding: 2px 8px;
                border-radius: 8px;
            }}
            
            #contextLabel[state="selection"] {{
                color: {t.success};
                background-color: {t.surface_hover};
                padding: 4px 12px;
                border-radius: 12px;
            }}
            
            #contextLabel[state="grouped"] {{
                color: {t.accent};
                background-color: {t.surface_hover};
                padding: 4px 12px;
                border-radius: 12px;
            }}
            
            /* ============ Drop Zones ============ */
            #XAxisZone {{
                background-color: {"#F0FDF4" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #GroupZone {{
                background-color: {"#F8FAFC" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #ValueZone {{
                background-color: {"#FAF5FF" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #HoverZone {{
                background-color: {"#FEFCE8" if t.is_light() else t.surface};
                border: none;
                border-radius: 8px;
            }}
            
            #zoneIcon {{
                font-size: 16px;
                background: transparent;
            }}
            
            #zoneHeader {{
                font-weight: 600;
                font-size: 13px;
                background: transparent;
                color: {t.foreground};
            }}
            
            #zoneHeader[zone="x"] {{
                color: {"#047857" if t.is_light() else t.success};
            }}
            
            #zoneHeader[zone="group"] {{
                color: {t.foreground};
            }}
            
            #zoneHeader[zone="value"] {{
                color: {"#581C87" if t.is_light() else "#A78BFA"};
            }}
            
            #zoneHeader[zone="hover"] {{
                color: {"#854D0E" if t.is_light() else t.warning};
            }}
            
            #zoneHelp {{
                font-size: 11px;
                background: transparent;
                color: {t.text_secondary};
            }}
            
            #zoneHelp[zone="x"] {{
                color: {"#059669" if t.is_light() else t.success};
            }}
            
            #zoneHelp[zone="group"] {{
                color: {t.text_secondary};
            }}
            
            #zoneHelp[zone="value"] {{
                color: {"#9333EA" if t.is_light() else "#A78BFA"};
            }}
            
            #zoneHelp[zone="hover"] {{
                color: {"#A16207" if t.is_light() else t.warning};
            }}
            
            #dropZone {{
                background-color: {t.surface};
                border: 2px dashed {t.border};
                border-radius: 8px;
                min-height: 50px;
            }}
            
            #dropZone[state="filled"] {{
                background-color: {t.selected};
                border: 2px solid {t.success};
            }}
            
            #dropZone[state="dragover"] {{
                background-color: {t.surface_hover};
                border: 2px solid {t.success};
            }}
            
            #placeholder {{
                color: {t.text_muted};
                font-size: 12px;
                font-style: italic;
                background: transparent;
            }}
            
            #chipList {{
                background: transparent;
                border: none;
                outline: none;
            }}
            
            /* ============ Zone Buttons ============ */
            #zoneClearBtn {{
                background: transparent;
                color: {t.success};
                border: 1px solid {t.success};
                border-radius: 6px;
                padding: 8px 12px;
                font-weight: 500;
                font-size: 11px;
            }}
            
            #zoneClearBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.success};
            }}
            
            #dangerButton {{
                background: transparent;
                color: {t.error};
                border: 1px solid {t.error};
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 500;
                font-size: 11px;
            }}
            
            #dangerButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.error};
            }}
            
            #warningButton {{
                background: transparent;
                color: {t.warning};
                border: 1px solid {t.warning};
                border-radius: 6px;
                padding: 6px 10px;
                font-weight: 500;
                font-size: 11px;
            }}
            
            #warningButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.warning};
            }}
            
            /* ============ Data Table ============ */
            #dataTableView {{
                background-color: {t.surface};
                alternate-background-color: {t.surface_hover};
                selection-background-color: {t.selected};
                selection-color: {t.foreground};
                gridline-color: {t.border_light};
                border: none;
                border-radius: 8px;
                color: {t.foreground};
            }}
            
            #dataTableView::item {{
                padding: 4px 8px;
                color: {t.foreground};
            }}
            
            #dataTableView::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            #dataTableView::item:hover {{
                background-color: {t.hover};
            }}
            
            #dataTableView QHeaderView::section {{
                background-color: {t.surface};
                border: none;
                border-bottom: 1px solid {t.border};
                padding: 6px 8px;
                font-weight: 600;
                font-size: 11px;
                color: {t.foreground};
            }}
            
            #dataTableView QHeaderView::section:hover {{
                background-color: {t.surface_hover};
            }}
            
            /* ============ Sliding Window ============ */
            #slidingWindow {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 4px;
            }}
            
            /* ============ Side-by-Side Layout ============ */
            #statsFrame {{
                background-color: {t.surface};
                border-radius: 4px;
                padding: 4px;
            }}
            
            #syncOptionsFrame {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            
            #graphPlaceholder {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                color: {t.foreground};
            }}
            
            /* ============ Floating Window ============ */
            #floatingHeader {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            
            #floatingTitle {{
                font-size: 14px;
                font-weight: 600;
                color: {t.foreground};
                background: transparent;
            }}
            
            #floatingFooter {{
                background-color: {t.surface};
                border-top: 1px solid {t.border};
            }}
            
            #floatingStatus {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
            }}
            
            #floatingGraphContainer {{
                background-color: {t.background};
            }}
            
            #headerButton {{
                background: transparent;
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 14px;
                color: {t.foreground};
            }}
            
            #headerButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.text_secondary};
            }}
            
            #headerButton:pressed {{
                background-color: {t.surface_active};
            }}
            
            #syncCheckbox {{
                color: {t.text_secondary};
                font-size: 12px;
                background: transparent;
            }}
            
            #headerSeparator {{
                background-color: {t.border};
            }}
            
            /* ============ Float Window ============ */
            #floatWindowHeader {{
                background-color: {t.surface};
                border-bottom: 1px solid {t.border};
            }}
            
            #dockButton {{
                background-color: {t.primary};
                color: white;
                border: none;
                border-radius: 4px;
                padding: 4px 12px;
                font-size: 11px;
                font-weight: 500;
            }}
            
            #dockButton:hover {{
                background-color: {t.accent};
            }}
            
            #dockButton:pressed {{
                background-color: {t.primary};
            }}
            
            #sectionTitle {{
                font-weight: 600;
                font-size: 13px;
                color: {t.foreground};
                padding: 4px;
                background: transparent;
            }}
            
            #floatButton {{
                background-color: {t.surface_hover};
                border: 1px solid {t.border};
                border-radius: 4px;
                font-size: 12px;
                color: {t.text_secondary};
            }}
            
            #floatButton:hover {{
                background-color: {t.surface_active};
                border-color: {t.text_secondary};
                color: {t.foreground};
            }}
            
            #floatPlaceholder {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #floatPlaceholderLabel {{
                color: {t.text_muted};
                font-size: 12px;
                background: transparent;
            }}
            
            /* ============ Chip Widget ============ */
            #chipWidget {{
                background-color: {t.surface};
                border: 1px solid {t.text_secondary};
                border-radius: 10px;
            }}
            
            #chipWidget:hover {{
                background-color: {t.surface_active};
                border-color: {t.primary};
            }}
            
            #chipLabel {{
                font-size: 11px;
                font-weight: 600;
                color: {t.foreground};
                background: transparent;
            }}
            
            #chipRemoveBtn {{
                background: transparent;
                color: {t.text_muted};
                border: none;
                font-size: 12px;
                font-weight: bold;
            }}
            
            #chipRemoveBtn:hover {{
                background-color: {"#FEE2E2" if t.is_light() else t.surface_active};
                color: {t.error};
                border-radius: 8px;
            }}
            
            #dragHandle {{
                font-size: 11px;
                color: {t.text_muted};
                background: transparent;
            }}
            
            /* ============ Value Chip Widget ============ */
            #valueChipWidget {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 10px;
            }}
            
            #valueChipWidget:hover {{
                background-color: {t.surface_hover};
            }}
            
            #valueNameLabel {{
                font-weight: 600;
                font-size: 11px;
                color: {t.foreground};
                background: transparent;
            }}
            
            /* ============ Dialogs ============ */
            #dialogHeader {{
                font-size: 16px;
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #dialogPanel {{
                background-color: {t.surface};
                border: 1px solid {t.border};
            }}
            
            #dialogPanelLeft {{
                background-color: {t.surface_hover};
                border-right: 1px solid {t.border};
            }}
            
            #dialogFooter {{
                background-color: {t.surface};
                border-top: 1px solid {t.border};
            }}
            
            #settingItem {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px;
            }}
            
            #settingItem:hover {{
                background-color: {t.surface_hover};
            }}
            
            #settingIcon {{
                font-size: 24px;
                background: transparent;
            }}
            
            #settingName {{
                font-weight: 600;
                color: {t.foreground};
                font-size: 13px;
                background: transparent;
            }}
            
            #settingDetail {{
                color: {t.text_secondary};
                font-size: 11px;
                background: transparent;
            }}
            
            #defaultBadge {{
                background-color: {"#FEF3C7" if t.is_light() else t.surface_active};
                color: {"#92400E" if t.is_light() else t.warning};
                font-size: 11px;
                padding: 2px 6px;
                border-radius: 4px;
            }}
            
            #actionButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 4px;
                font-size: 14px;
                color: {t.foreground};
            }}
            
            #actionButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.border};
            }}
            
            #primaryButton {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 600;
            }}
            
            #primaryButton:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.accent}, stop:1 {t.primary});
            }}
            
            #secondaryButton {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 8px 16px;
            }}
            
            #secondaryButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            #deleteButton {{
                background-color: {"#FEE2E2" if t.is_light() else t.surface};
                color: {t.error};
                border: 1px solid {t.error};
                border-radius: 6px;
                padding: 8px 16px;
            }}
            
            #deleteButton:hover {{
                background-color: {t.error};
                color: white;
            }}
            
            /* ============ Profile Bar ============ */
            #profileBar {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #profileIcon {{
                font-size: 18px;
                background: transparent;
            }}
            
            #profileName {{
                font-weight: 600;
                font-size: 13px;
                color: {t.foreground};
                background: transparent;
            }}
            
            #profileActiveLabel {{
                color: {t.success};
                font-size: 12px;
            }}
            
            #profileActionBtn {{
                background: transparent;
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                color: {t.text_secondary};
            }}
            
            #profileActionBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
                color: {t.primary};
            }}
            
            #profileLabel {{
                color: {t.text_secondary};
                font-size: 12px;
                background: transparent;
            }}
            
            /* ============ Dataset Manager ============ */
            #datasetItem {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #datasetItem:hover {{
                background-color: {t.surface_hover};
            }}
            
            #datasetItem[active="true"] {{
                border: 2px solid {t.success};
            }}
            
            #datasetName {{
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #datasetActiveLabel {{
                color: {t.success};
                font-size: 12px;
            }}
            
            #datasetStat {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #datasetRemoveBtn {{
                color: {t.error};
            }}
            
            #datasetTitle {{
                font-size: 14px;
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #datasetTree {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #datasetAddBtn {{
                background-color: {t.primary};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 8px 16px;
            }}
            
            #datasetAddBtn:hover {{
                background-color: {t.accent};
            }}
            
            /* ============ Overlay Stats ============ */
            #overlayStatsWidget {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            #overlayTitle {{
                font-weight: bold;
                font-size: 12px;
                color: {t.foreground};
            }}
            
            #overlayStatLabel {{
                font-size: 11px;
                color: {t.text_muted};
            }}
            
            #overlayStatValue {{
                font-size: 11px;
                color: {t.foreground};
            }}
            
            #overlayStatPositive {{
                font-size: 11px;
                font-weight: bold;
                color: {t.success};
            }}
            
            /* ============ Comparison Panel ============ */
            #guideText {{
                padding: 4px;
                background-color: {t.surface_hover};
                border-radius: 4px;
                color: {t.foreground};
            }}
            
            #diffSummary {{
                padding: 8px;
                background-color: {t.surface_hover};
                border-radius: 4px;
                color: {t.foreground};
            }}
            
            /* ============ Search Input ============ */
            #searchInput {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                padding-right: 32px;
                placeholder-text-color: {t.text_secondary};
            }}
            
            #searchInput:focus {{
                border: 2px solid {t.primary};
            }}
            
            #searchClearBtn {{
                background: transparent;
                border: none;
                color: {t.text_muted};
                font-size: 14px;
            }}
            
            #searchClearBtn:hover {{
                color: {t.foreground};
            }}
            
            #searchResultLabel {{
                font-size: 11px;
                color: {t.text_muted};
                background: transparent;
            }}
            
            #searchResultLabel[state="found"] {{
                color: {t.success};
            }}
            
            #searchResultLabel[state="notfound"] {{
                color: {t.error};
            }}
            
            /* ============ Limit Marking Button ============ */
            #limitMarkingBtn {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 4px;
                padding: 4px 8px;
                font-size: 11px;
                color: {t.text_secondary};
            }}
            
            #limitMarkingBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            #limitMarkingBtn:checked {{
                background-color: {t.selected};
                border-color: {t.primary};
                color: {t.primary};
            }}
            
            /* ============ Window/Group Info Labels ============ */
            #windowLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #groupInfoLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #groupInfoLabel[state="grouped"] {{
                color: {t.primary};
                font-weight: 500;
            }}
            
            /* ============ Splitter ============ */
            #themeSplitter::handle {{
                background-color: {t.text_muted if not t.is_light() else t.border};
            }}
            
            /* ============ Toolbar Labels ============ */
            #toolbarLabel {{
                color: {t.text_secondary};
                font-size: 12px;
            }}
            
            /* ============ Max Points Label ============ */
            #maxPointsLabel {{
                font-weight: 600;
                color: {t.accent};
            }}
            
            /* ============ Error/Warning Labels ============ */
            #errorLabel {{
                color: {t.error};
            }}
            
            #warningLabel {{
                color: {t.warning};
            }}
            
            #successLabel {{
                color: {t.success};
            }}
            
            /* ============ Parsing Preview ============ */
            #previewHeader {{
                font-size: 16px;
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #etlStatusLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #etlStatusLabel[state="success"] {{
                color: {t.success};
            }}
            
            #etlStatusLabel[state="error"] {{
                color: {t.error};
            }}
            
            #statsCountLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            #columnCountLabel {{
                color: {t.text_secondary};
                font-size: 11px;
            }}
            
            /* ============ Save Setting Dialog ============ */
            #dialogLine {{
                background-color: {t.border};
            }}
            
            #inputLabel {{
                font-weight: 500;
                color: {t.foreground};
            }}
            
            #optionsFrame {{
                background-color: {t.surface_hover};
                border-radius: 8px;
            }}
            
            #optionCheckbox {{
                color: {t.text_secondary};
            }}
            
            /* ============ Multi File Dialog ============ */
            #fileHeader {{
                color: {t.text_muted};
            }}
            
            #summaryLabel {{
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #warningBox {{
                color: {"#f57c00" if t.is_light() else t.warning};
                padding: 8px;
                background-color: {"#fff3e0" if t.is_light() else t.surface_hover};
                border-radius: 4px;
            }}
            
            /* ============ Report Dialog ============ */
            #generateBtn {{
                background-color: {t.success};
                color: white;
                border: none;
                border-radius: 8px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
            }}
            
            #generateBtn:hover {{
                background-color: {"#059669" if t.is_light() else "#34D399"};
            }}
            
            /* ============ Drawing ============ */
            #drawingStyleFrame {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}
            
            /* ============ Dashboard ============ */
            #dashboardTitle {{
                font-weight: bold;
                color: {t.foreground};
            }}
            
            #chartArea {{
                background-color: {t.surface_hover};
            }}
            
            /* ============ Side by Side Header ============ */
            #datasetHeaderFrame {{
                border-radius: 4px;
            }}
            
            #datasetHeaderName {{
                color: white;
                font-weight: bold;
            }}
            
            #datasetHeaderRows {{
                color: rgba(255,255,255,0.8);
            }}
            
            /* ============ Empty State (New) ============ */
            #emptyStateWidget {{
                background-color: {t.background};
            }}
            
            #emptyStateCard {{
                background-color: {t.surface};
                border: {"1px solid " + t.border if t.is_light() else "none"};
                border-radius: 16px;
            }}
            
            #emptyStateIcon {{
                background: transparent;
                border: none;
            }}
            
            #emptyStateTitle {{
                font-size: 24px;
                font-weight: 700;
                color: {t.foreground};
                background: transparent;
                border: none;
                margin-top: 8px;
            }}
            
            #emptyStateSubtitle {{
                font-size: 15px;
                color: {t.text_secondary};
                background: transparent;
                border: none;
                line-height: 1.5;
            }}
            
            #emptyStateFormats {{
                font-size: 12px;
                color: {t.text_muted};
                background: transparent;
                border: none;
                margin-top: 4px;
            }}
            
            #emptyStatePrimaryBtn {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                color: white;
                border: none;
                border-radius: 10px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 600;
                min-width: 120px;
            }}
            
            #emptyStatePrimaryBtn:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.accent}, stop:1 {t.primary});
            }}
            
            #emptyStateSecondaryBtn {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 10px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: 500;
                min-width: 120px;
            }}
            
            #emptyStateSecondaryBtn:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            #emptyStateDropHint {{
                background-color: {"#F0FDF4" if t.is_light() else "rgba(16, 185, 129, 0.1)"};
                border: 2px dashed {"#86EFAC" if t.is_light() else t.success};
                border-radius: 12px;
            }}
            
            #dropHintIcon {{
                font-size: 24px;
                background: transparent;
                border: none;
            }}
            
            #dropHintText {{
                font-size: 13px;
                color: {t.success};
                background: transparent;
                border: none;
            }}
            
            #emptyStateStepsTitle {{
                font-size: 13px;
                font-weight: 600;
                color: {t.text_secondary};
                background: transparent;
                border: none;
                margin-bottom: 8px;
            }}
            
            #stepNumber {{
                font-size: 16px;
                background: transparent;
                border: none;
            }}
            
            #stepText {{
                font-size: 13px;
                color: {t.text_secondary};
                background: transparent;
                border: none;
            }}
            
            /* ============ Drop Overlay ============ */
            #dropZoneOverlay {{
                background-color: rgba({self._hex_to_rgb(t.primary)}, 0.15);
                border: 3px dashed {t.primary};
            }}
            
            #dropOverlayIcon {{
                background: transparent;
                border: none;
            }}
            
            #dropOverlayText {{
                font-size: 18px;
                font-weight: 600;
                color: {t.primary};
                background: transparent;
                border: none;
            }}
            
            /* ============ Improved Drop Zones ============ */
            #XAxisZone {{
                background-color: {"#ECFDF5" if t.is_light() else "rgba(16, 185, 129, 0.08)"};
                border: 2px dashed {"#A7F3D0" if t.is_light() else "rgba(16, 185, 129, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #XAxisZone[state="filled"] {{
                background-color: {"#D1FAE5" if t.is_light() else "rgba(16, 185, 129, 0.15)"};
                border: 2px solid {t.success};
            }}
            
            #XAxisZone[state="dragover"] {{
                background-color: {"#A7F3D0" if t.is_light() else "rgba(16, 185, 129, 0.25)"};
                border: 2px solid {t.success};
            }}
            
            #GroupZone {{
                background-color: {"#F8FAFC" if t.is_light() else "rgba(148, 163, 184, 0.08)"};
                border: 2px dashed {"#CBD5E1" if t.is_light() else "rgba(148, 163, 184, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #GroupZone[state="filled"] {{
                background-color: {"#E2E8F0" if t.is_light() else "rgba(148, 163, 184, 0.15)"};
                border: 2px solid {t.text_secondary};
            }}
            
            #ValueZone {{
                background-color: {"#EEF2FF" if t.is_light() else "rgba(99, 102, 241, 0.08)"};
                border: 2px dashed {"#C7D2FE" if t.is_light() else "rgba(99, 102, 241, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #ValueZone[state="filled"] {{
                background-color: {"#E0E7FF" if t.is_light() else "rgba(99, 102, 241, 0.15)"};
                border: 2px solid {t.primary};
            }}
            
            #HoverZone {{
                background-color: {"#FFFBEB" if t.is_light() else "rgba(245, 158, 11, 0.08)"};
                border: 2px dashed {"#FDE68A" if t.is_light() else "rgba(245, 158, 11, 0.3)"};
                border-radius: 12px;
                padding: 12px;
            }}
            
            #HoverZone[state="filled"] {{
                background-color: {"#FEF3C7" if t.is_light() else "rgba(245, 158, 11, 0.15)"};
                border: 2px solid {t.warning};
            }}
            
            /* ============ Enhanced Placeholder Text ============ */
            #placeholder {{
                color: {t.text_muted};
                font-size: 13px;
                font-weight: 500;
                background: transparent;
            }}
            
            /* ============ Graph Area Enhancement ============ */
            #graphAreaFrame {{
                background-color: {t.background};
                border-radius: 8px;
            }}

            /* ============ Empty State Shortcut Hint ============ */
            #emptyStateShortcutHint {{
                color: {t.text_muted};
                font-size: 11px;
                font-weight: 500;
                background-color: {t.surface_hover};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 3px 10px;
                max-width: 80px;
            }}

            /* ============ Status Bar Enhancements ============ */
            #statusVersionLabel {{
                color: {t.text_muted};
                font-size: 11px;
                padding: 2px 8px;
                background: transparent;
                border: none;
            }}

            #statusThemeLabel {{
                color: {t.primary};
                font-size: 11px;
                font-weight: 500;
                padding: 2px 8px;
                background: transparent;
                border: none;
            }}

            #statusThemeLabel:hover {{
                color: {t.accent};
            }}

            #statusSeparator {{
                color: {t.border};
                background-color: {t.border};
                max-width: 1px;
                margin: 4px 4px;
                border: none;
                border-radius: 0px;
            }}

            #statusMemoryLabel {{
                font-size: 11px;
                font-weight: 500;
                padding: 2px 8px;
                border-radius: 8px;
                border: none;
                background: transparent;
            }}

            #statusMemoryLabel[level="normal"] {{
                color: {t.success};
                background-color: {"#ECFDF5" if t.is_light() else "rgba(16, 185, 129, 0.12)"};
            }}

            #statusMemoryLabel[level="warning"] {{
                color: {t.warning};
                background-color: {"#FFFBEB" if t.is_light() else "rgba(245, 158, 11, 0.12)"};
            }}

            #statusMemoryLabel[level="danger"] {{
                color: {t.error};
                background-color: {"#FEF2F2" if t.is_light() else "rgba(239, 68, 68, 0.12)"};
            }}

            /* ============ Toolbar Group Labels ============ */
            #toolbarGroupLabel {{
                color: {t.text_muted};
                font-size: 11px;
                font-weight: 600;
                padding: 0px 4px;
                background: transparent;
                border: none;
            }}

            /* ============ About Dialog ============ */
            #aboutDialog {{
                background-color: {t.background};
            }}

            #aboutContent {{
                background-color: {t.background};
            }}

            #aboutTagline {{
                font-size: 14px;
                color: {t.text_secondary};
                background: transparent;
                border: none;
            }}

            #aboutFeaturesFrame {{
                background: transparent;
                border: none;
            }}

            #aboutFeatureCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
            }}

            #aboutFeatureCard:hover {{
                background-color: {t.surface_hover};
            }}

            #aboutFeatureTitle {{
                font-weight: 600;
                font-size: 12px;
                color: {t.foreground};
                background: transparent;
                border: none;
            }}

            #aboutFeatureDesc {{
                font-size: 11px;
                color: {t.text_secondary};
                background: transparent;
                border: none;
            }}

            #aboutBuiltLabel {{
                font-size: 11px;
                font-weight: 600;
                color: {t.text_muted};
                background: transparent;
                border: none;
            }}

            #aboutTechChip {{
                font-size: 11px;
                color: {t.text_secondary};
                background-color: {t.surface_hover};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 3px 8px;
            }}

            #aboutCopyright {{
                font-size: 11px;
                color: {t.text_muted};
                background: transparent;
                border: none;
            }}

            #aboutCloseBtn {{
                min-width: 80px;
            }}

            /* ============ Enhanced Stat Cards ============ */
            #StatCard {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 10px;
            }}

            #StatCard:hover {{
                background-color: {t.surface_hover};
            }}

            #cardValue {{
                color: {t.foreground};
                font-size: 20px;
                font-weight: 700;
                background: transparent;
                border: none;
            }}

            /* ============ Enhanced Toolbar ============ */
            QToolButton:checked {{
                background-color: {t.selected};
                color: {t.primary};
                border: 1px solid {t.primary}40;
            }}

            QToolBar::separator {{
                width: 1px;
                background-color: {t.border};
                margin: 8px 12px;
            }}

            QToolBar::handle {{
                background: {t.border};
                width: 6px;
                border-radius: 3px;
                margin: 6px 2px;
            }}

            #toolbarCustomizeDialog {{
                background-color: {t.background};
            }}

            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 6px;
                padding: 6px 10px;
                font-size: 15px;
            }}

            /* ============ Thinner Scrollbars ============ */
            QScrollBar:vertical {{
                background-color: transparent;
                width: 8px;
                margin: 4px;
            }}

            QScrollBar::handle:vertical {{
                background-color: {t.text_muted};
                border-radius: 4px;
                min-height: 30px;
            }}

            QScrollBar:horizontal {{
                background-color: transparent;
                height: 8px;
                margin: 4px;
            }}

            QScrollBar::handle:horizontal {{
                background-color: {t.text_muted};
                border-radius: 4px;
                min-width: 30px;
            }}
        """
    
    def _hex_to_rgb(self, hex_color: str) -> str:
        """Convert hex color to RGB values for rgba()"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
            return f"{r}, {g}, {b}"
        return "0, 0, 0"
    
    # ==================== Theme Toggle (PRD §3.6) ====================

    _VALID_PREFERENCES = {"light", "dark", "system"}

    @property
    def theme_preference(self) -> str:
        """현재 테마 선호 설정 ('light', 'dark', 'system')"""
        return self._theme_preference

    def set_theme_preference(self, preference: str) -> None:
        """
        FR-6.1 ~ FR-6.4: 테마 선호 설정.

        유효하지 않은 값은 무시 (기존 유지).
        """
        if preference not in self._VALID_PREFERENCES:
            return
        self._theme_preference = preference

        # 내부 _current도 연동 (tailwind / tailwind-dark 매핑)
        resolved = self.resolve_theme()
        if resolved.is_light():
            if 'tailwind' in self._themes:
                self._current = 'tailwind'
            else:
                self._current = 'light'
        else:
            if 'tailwind-dark' in self._themes:
                self._current = 'tailwind-dark'
            else:
                self._current = 'dark'

    def resolve_theme(self) -> Theme:
        """
        현재 preference에 따라 실제 적용할 Theme 반환.

        - 'light'  → Tailwind (light)
        - 'dark'   → Tailwind Dark
        - 'system' → OS 다크모드 감지 후 결정
          - ERR-6.1: OS 감지 실패 → light 폴백
        """
        if self._theme_preference == "light":
            return self._themes.get('tailwind', TAILWIND_THEME)
        elif self._theme_preference == "dark":
            return self._themes.get('tailwind-dark', TAILWIND_DARK_THEME)
        else:
            # system mode
            try:
                is_dark = self._detect_system_dark_mode()
            except Exception:
                # ERR-6.1: 감지 실패 → light 폴백
                is_dark = False

            if is_dark:
                return self._themes.get('tailwind-dark', TAILWIND_DARK_THEME)
            else:
                return self._themes.get('tailwind', TAILWIND_THEME)

    def _detect_system_dark_mode(self) -> bool:
        """
        FR-6.4: macOS 시스템 다크모드 감지.

        subprocess로 defaults 명령 사용. 실패 시 예외 발생.
        """
        import subprocess
        try:
            result = subprocess.run(
                ["defaults", "read", "-g", "AppleInterfaceStyle"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.returncode == 0 and "Dark" in result.stdout
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as e:
            raise RuntimeError(f"Failed to detect system dark mode: {e}") from e

    def get_graph_colors(self) -> Dict[str, str]:
        """
        FR-6.5: pyqtgraph 배경/전경 색상 반환.

        Returns:
            Dict with 'background' and 'foreground' keys.
        """
        theme = self.resolve_theme()
        return {
            "background": theme.background,
            "foreground": theme.foreground,
        }

    def get_theme(self) -> str:
        """
        FR-6.7: IPC `get_theme` 지원.

        Returns:
            현재 theme_preference ('light', 'dark', 'system')
        """
        return self._theme_preference

    # ==================== Persistence ====================

    def to_dict(self) -> Dict:
        return {
            'current': self._current,
            'theme_preference': self._theme_preference,
            'custom_themes': {
                k: v.to_dict()
                for k, v in self._themes.items()
                if k not in self.BUILTIN_THEMES
            },
        }

    def from_dict(self, data) -> None:
        """
        설정 복원. ERR-6.2: 손상 시 기본값 폴백.

        - None / dict가 아닌 입력 → 무시
        - 유효하지 않은 preference → 무시
        - 유효하지 않은 current → 무시
        """
        if not isinstance(data, dict):
            return

        # Restore theme_preference
        pref = data.get('theme_preference')
        if pref in self._VALID_PREFERENCES:
            self._theme_preference = pref

        # Restore current (internal theme id)
        current = data.get('current')
        if current and current in self._themes:
            self._current = current

        # Restore custom themes
        custom = data.get('custom_themes')
        if isinstance(custom, dict):
            for theme_id, theme_data in custom.items():
                try:
                    self._themes[theme_id] = Theme.from_dict(theme_data)
                except Exception:
                    pass  # ERR-6.2: 손상 무시
