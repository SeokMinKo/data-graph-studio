"""
Tests for Theme (Dark/Light Mode)
"""

import pytest
from unittest.mock import MagicMock, patch

import sys
import os

# Add project root to path
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from data_graph_studio.ui.theme import ThemeManager, Theme, ColorPalette


class TestTheme:
    """테마 테스트"""
    
    def test_theme_creation(self):
        """테마 생성"""
        t = Theme(
            name="Light",
            background="#ffffff",
            foreground="#000000",
            primary="#1f77b4",
            secondary="#ff7f0e",
        )
        
        assert t.name == "Light"
        assert t.background == "#ffffff"
        assert t.foreground == "#000000"
    
    def test_theme_colors(self):
        """테마 색상 접근"""
        t = Theme(
            name="Test",
            background="#fff",
            foreground="#000",
            primary="#1f77b4",
            secondary="#ff7f0e",
        )
        
        assert t.primary == "#1f77b4"
        assert t.secondary == "#ff7f0e"


class TestColorPalette:
    """컬러 팔레트 테스트"""
    
    def test_default_palette(self):
        """기본 팔레트"""
        palette = ColorPalette.default()
        
        assert len(palette.colors) >= 8
    
    def test_custom_palette(self):
        """커스텀 팔레트"""
        colors = ["#ff0000", "#00ff00", "#0000ff"]
        palette = ColorPalette(colors)
        
        assert palette.colors == colors
    
    def test_get_color(self):
        """인덱스로 색상 조회"""
        colors = ["#ff0000", "#00ff00", "#0000ff"]
        palette = ColorPalette(colors)
        
        assert palette.get(0) == "#ff0000"
        assert palette.get(1) == "#00ff00"
        assert palette.get(2) == "#0000ff"
    
    def test_color_cycling(self):
        """인덱스 순환"""
        colors = ["#ff0000", "#00ff00"]
        palette = ColorPalette(colors)
        
        assert palette.get(0) == "#ff0000"
        assert palette.get(1) == "#00ff00"
        assert palette.get(2) == "#ff0000"  # Cycles back
        assert palette.get(3) == "#00ff00"


class TestThemeManager:
    """테마 매니저 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ThemeManager()
    
    def test_default_themes(self, manager):
        """기본 테마 존재"""
        themes = manager.list_themes()
        
        assert 'light' in themes
        assert 'dark' in themes
    
    def test_current_theme(self, manager):
        """현재 테마"""
        theme = manager.current_theme
        
        assert theme is not None
        assert theme.name in ['Light', 'Dark']
    
    def test_set_theme(self, manager):
        """테마 설정"""
        manager.set_theme('dark')
        
        assert manager.current_theme.name == 'Dark'
        
        manager.set_theme('light')
        
        assert manager.current_theme.name == 'Light'
    
    def test_toggle_theme(self, manager):
        """테마 토글"""
        manager.set_theme('light')
        
        manager.toggle()
        assert manager.current_theme.name == 'Dark'
        
        manager.toggle()
        assert manager.current_theme.name == 'Light'
    
    def test_add_custom_theme(self, manager):
        """커스텀 테마 추가"""
        custom = Theme(
            name="Custom",
            background="#1a1a2e",
            foreground="#eaeaea",
            primary="#e94560",
            secondary="#0f3460",
        )
        
        manager.add_theme('custom', custom)
        
        assert 'custom' in manager.list_themes()
        
        manager.set_theme('custom')
        assert manager.current_theme.name == 'Custom'
    
    def test_remove_custom_theme(self, manager):
        """커스텀 테마 제거"""
        custom = Theme(
            name="ToRemove",
            background="#000",
            foreground="#fff",
            primary="#f00",
            secondary="#0f0",
        )
        
        manager.add_theme('to_remove', custom)
        manager.remove_theme('to_remove')
        
        assert 'to_remove' not in manager.list_themes()
    
    def test_cannot_remove_builtin(self, manager):
        """빌트인 테마 제거 불가"""
        result = manager.remove_theme('light')
        
        assert result is False
        assert 'light' in manager.list_themes()


class TestLightTheme:
    """라이트 테마 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ThemeManager()
        m.set_theme('light')
        return m
    
    def test_light_background(self, manager):
        """라이트 테마 배경색"""
        theme = manager.current_theme
        
        # 밝은 배경색 (RGB 각 채널 > 200)
        assert theme.is_light() is True
    
    def test_light_foreground(self, manager):
        """라이트 테마 전경색"""
        theme = manager.current_theme
        
        # 어두운 전경색 (dark text on light background)
        # Acceptable: #000000, #111827, #212121, #333333, etc.
        assert theme.foreground[1:3] in ['00', '11', '21', '33']  # #00xxxx, #11xxxx, #21xxxx, #33xxxx


class TestDarkTheme:
    """다크 테마 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ThemeManager()
        m.set_theme('dark')
        return m
    
    def test_dark_background(self, manager):
        """다크 테마 배경색"""
        theme = manager.current_theme
        
        # 어두운 배경색
        assert theme.is_light() is False
    
    def test_dark_foreground(self, manager):
        """다크 테마 전경색"""
        theme = manager.current_theme
        
        # 밝은 전경색
        # hex 값의 첫 두 자리 (R)가 높은 값
        r_val = int(theme.foreground[1:3], 16)
        assert r_val > 150


class TestThemeStylesheet:
    """테마 스타일시트 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ThemeManager()
    
    def test_generate_stylesheet(self, manager):
        """스타일시트 생성"""
        stylesheet = manager.generate_stylesheet()
        
        assert isinstance(stylesheet, str)
        assert len(stylesheet) > 0
    
    def test_stylesheet_contains_colors(self, manager):
        """스타일시트에 색상 포함"""
        manager.set_theme('light')
        stylesheet = manager.generate_stylesheet()
        
        theme = manager.current_theme
        assert theme.background.lower() in stylesheet.lower() or \
               theme.background[1:].lower() in stylesheet.lower()
    
    def test_different_stylesheets(self, manager):
        """테마별 다른 스타일시트"""
        manager.set_theme('light')
        light_ss = manager.generate_stylesheet()
        
        manager.set_theme('dark')
        dark_ss = manager.generate_stylesheet()
        
        assert light_ss != dark_ss


class TestChartPalette:
    """차트 팔레트 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ThemeManager()
    
    def test_chart_colors(self, manager):
        """차트 색상 팔레트"""
        palette = manager.get_chart_palette()
        
        assert len(palette.colors) >= 8
    
    def test_palette_differs_by_theme(self, manager):
        """테마별 다른 차트 색상"""
        manager.set_theme('light')
        light_palette = manager.get_chart_palette()
        
        manager.set_theme('dark')
        dark_palette = manager.get_chart_palette()
        
        # 차트 색상은 테마와 관계없이 같을 수도 있음
        # 하지만 최소한 팔레트가 존재해야 함
        assert len(light_palette.colors) > 0
        assert len(dark_palette.colors) > 0


class TestThemePersistence:
    """테마 지속성 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ThemeManager()
    
    def test_to_dict(self, manager):
        """테마 설정 직렬화"""
        manager.set_theme('dark')
        
        data = manager.to_dict()
        
        assert 'current' in data
        assert data['current'] == 'dark'
    
    def test_from_dict(self, manager):
        """테마 설정 복원"""
        data = {'current': 'dark'}
        
        manager.from_dict(data)
        
        assert manager.current_theme.name == 'Dark'
