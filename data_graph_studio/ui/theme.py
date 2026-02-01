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
    accent: str = "#3A7AFE"       # Indigo
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
        
        # Surface colors
        if not self.surface:
            self.surface = "#FFFFFF" if is_light else "#1F2937"
        if not self.surface_hover:
            self.surface_hover = "#F9FAFB" if is_light else "#222222"
        if not self.surface_active:
            self.surface_active = "#EFEFEF" if is_light else "#4B5563"
        
        # Borders
        if not self.border:
            self.border = "#E6E6E6" if is_light else "#222222"
        if not self.border_light:
            self.border_light = "#EFEFEF" if is_light else "#1F2937"
        
        # Interactive
        if not self.hover:
            self.hover = "#EFEFEF" if is_light else "#222222"
        if not self.selected:
            self.selected = self.primary + "20"  # 12% opacity
        if not self.focused:
            self.focused = self.primary + "30"
        
        # Text
        if not self.text_primary:
            self.text_primary = self.foreground
        if not self.text_secondary:
            self.text_secondary = "#666666" if is_light else "#9CA3AF"
        if not self.text_muted:
            self.text_muted = "#9CA3AF" if is_light else "#666666"
        if not self.text_disabled:
            self.text_disabled = "#D1D5DB" if is_light else "#4B5563"
        
        # Shadow
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
            "#3A7AFE",  # Indigo
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
            "#3A7AFE",  # Indigo
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

# Light Theme - Clean & Minimal
LIGHT_THEME = Theme(
    name="Light",
    background="#F9FAFB",
    foreground="#111827",
    primary="#3A7AFE",
    secondary="#EC4899",
    surface="#FFFFFF",
    border="#E6E6E6",
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


class ThemeManager:
    """Modern Theme Manager with animations support"""
    
    BUILTIN_THEMES = {'light', 'dark', 'midnight'}
    
    def __init__(self):
        self._themes: Dict[str, Theme] = {
            'light': LIGHT_THEME,
            'dark': DARK_THEME,
            'midnight': MIDNIGHT_THEME,
        }
        self._current: str = 'light'
        self._chart_palette: ColorPalette = ColorPalette.default()
    
    @property
    def current_theme(self) -> Theme:
        return self._themes[self._current]
    
    def list_themes(self) -> List[str]:
        return list(self._themes.keys())
    
    def set_theme(self, theme_id: str):
        if theme_id in self._themes:
            self._current = theme_id
    
    def toggle(self):
        if self._current == 'light':
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
                font-family: 'Segoe UI', 'SF Pro Display', -apple-system, BlinkMacSystemFont, sans-serif;
                font-size: 13px;
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
                border: none;
                border-radius: 8px;
            }}
            
            QFrame[frameShape="4"] {{  /* StyledPanel */
                background-color: {t.surface};
                border: none;
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
                background-color: {t.border};
                border-radius: 5px;
                min-height: 30px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background-color: {t.text_secondary};
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
                background-color: {t.border};
                border-radius: 5px;
                min-width: 30px;
            }}
            
            QScrollBar::handle:horizontal:hover {{
                background-color: {t.text_secondary};
            }}
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            
            /* ============ Splitter ============ */
            QSplitter::handle {{
                background-color: transparent;
            }}
            
            QSplitter::handle:hover {{
                background-color: {t.primary}40;
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
        """
    
    def to_dict(self) -> Dict:
        return {
            'current': self._current,
            'custom_themes': {
                k: v.to_dict()
                for k, v in self._themes.items()
                if k not in self.BUILTIN_THEMES
            },
        }
    
    def from_dict(self, data: Dict):
        if 'current' in data and data['current'] in self._themes:
            self._current = data['current']
        
        if 'custom_themes' in data:
            for theme_id, theme_data in data['custom_themes'].items():
                self._themes[theme_id] = Theme.from_dict(theme_data)
