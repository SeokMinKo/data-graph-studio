"""
Theme - Modern Light/Dark Mode with Glassmorphism and Soft UI
"""

from typing import Dict, List
from dataclasses import dataclass


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
            self.text_muted = "#9CA3AF" if is_light else "#6B7280"
        if not self.text_disabled:
            self.text_disabled = "#D1D5DB" if is_light else "#4B5563"
        
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
    text_muted="#9CA3AF",
    text_disabled="#D1D5DB",
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
    text_muted="#94A3B8",        # slate-400
    text_disabled="#CBD5E1",     # slate-300
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
    text_muted="#64748B",        # slate-500
    text_disabled="#334155",     # slate-700
    shadow_color="rgba(0, 0, 0, 0.30)",
    gradient_start="#818CF8",    # indigo-400
    gradient_end="#A78BFA",      # violet-400
)


class ThemeManager:
    """Modern Theme Manager with animations support"""
    
    BUILTIN_THEMES = {'light', 'dark', 'midnight', 'tailwind', 'tailwind-dark'}
    
    def __init__(self):
        self._themes: Dict[str, Theme] = {
            'light': LIGHT_THEME,
            'dark': DARK_THEME,
            'midnight': MIDNIGHT_THEME,
            'tailwind': TAILWIND_THEME,
            'tailwind-dark': TAILWIND_DARK_THEME,
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
        from ._theme_base_stylesheet import base_stylesheet
        return base_stylesheet(self.current_theme)

    
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
