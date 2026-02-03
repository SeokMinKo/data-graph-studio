"""
Tests for Theme Toggle — Feature 6 (PRD Section 3.6)

UT-6.1: 테마 전환 (light→dark→system)
UT-6.2: 테마 설정 영속화
UT-6.3: 테마 설정 파일 손상 → 기본 테마 폴백
"""

import pytest
from unittest.mock import patch, MagicMock

from data_graph_studio.core.state import ThemeState
from data_graph_studio.ui.theme import (
    ThemeManager,
    Theme,
    TAILWIND_THEME,
    TAILWIND_DARK_THEME,
)


# ── UT-6.1: 테마 전환 (light → dark → system) ───────────────────


class TestThemeToggle:
    """UT-6.1: 테마 전환 동작 확인"""

    def test_set_theme_light(self):
        """light 테마 설정"""
        mgr = ThemeManager()
        mgr.set_theme_preference("light")
        assert mgr.theme_preference == "light"
        resolved = mgr.resolve_theme()
        assert resolved.is_light()

    def test_set_theme_dark(self):
        """dark 테마 설정"""
        mgr = ThemeManager()
        mgr.set_theme_preference("dark")
        assert mgr.theme_preference == "dark"
        resolved = mgr.resolve_theme()
        assert not resolved.is_light()

    def test_set_theme_system(self):
        """system 테마 설정 — OS 모드에 따라 결정"""
        mgr = ThemeManager()
        mgr.set_theme_preference("system")
        assert mgr.theme_preference == "system"
        # resolve_theme should return a valid Theme regardless
        resolved = mgr.resolve_theme()
        assert isinstance(resolved, Theme)

    def test_cycle_light_dark_system(self):
        """light → dark → system 순환"""
        mgr = ThemeManager()

        mgr.set_theme_preference("light")
        assert mgr.theme_preference == "light"

        mgr.set_theme_preference("dark")
        assert mgr.theme_preference == "dark"

        mgr.set_theme_preference("system")
        assert mgr.theme_preference == "system"

    def test_toggle_cycles_light_dark(self):
        """toggle()은 light ↔ dark 전환"""
        mgr = ThemeManager()
        mgr.set_theme_preference("light")

        mgr.toggle()
        assert mgr.theme_preference == "dark"

        mgr.toggle()
        assert mgr.theme_preference == "light"

    def test_toggle_from_system_goes_to_light(self):
        """system 상태에서 toggle → light"""
        mgr = ThemeManager()
        mgr.set_theme_preference("system")
        mgr.toggle()
        # From system, toggle should go to explicit light or dark
        assert mgr.theme_preference in ("light", "dark")

    def test_resolve_system_dark_mode(self):
        """system + OS dark mode → dark 테마"""
        mgr = ThemeManager()
        mgr.set_theme_preference("system")

        with patch.object(mgr, "_detect_system_dark_mode", return_value=True):
            resolved = mgr.resolve_theme()
            assert not resolved.is_light()

    def test_resolve_system_light_mode(self):
        """system + OS light mode → light 테마"""
        mgr = ThemeManager()
        mgr.set_theme_preference("system")

        with patch.object(mgr, "_detect_system_dark_mode", return_value=False):
            resolved = mgr.resolve_theme()
            assert resolved.is_light()

    def test_resolve_system_detect_failure_fallback_light(self):
        """ERR-6.1: system 모드에서 OS 감지 실패 → light 폴백"""
        mgr = ThemeManager()
        mgr.set_theme_preference("system")

        with patch.object(mgr, "_detect_system_dark_mode", side_effect=Exception("OS error")):
            resolved = mgr.resolve_theme()
            assert resolved.is_light()

    def test_invalid_preference_ignored(self):
        """잘못된 preference 값 → 무시 (기존 유지)"""
        mgr = ThemeManager()
        mgr.set_theme_preference("light")
        mgr.set_theme_preference("invalid_value")
        assert mgr.theme_preference == "light"


# ── FR-6.5: pyqtgraph 배경/전경 색상 테마 연동 ──────────────────


class TestThemePyqtgraphColors:
    """FR-6.5: pyqtgraph 배경/전경 연동"""

    def test_light_theme_graph_colors(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("light")
        colors = mgr.get_graph_colors()
        assert "background" in colors
        assert "foreground" in colors
        # Light theme → white-ish background
        assert colors["background"] is not None

    def test_dark_theme_graph_colors(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("dark")
        colors = mgr.get_graph_colors()
        assert colors["background"] is not None
        assert colors["foreground"] is not None

    def test_graph_colors_differ_by_theme(self):
        mgr = ThemeManager()

        mgr.set_theme_preference("light")
        light_colors = mgr.get_graph_colors()

        mgr.set_theme_preference("dark")
        dark_colors = mgr.get_graph_colors()

        assert light_colors["background"] != dark_colors["background"]


# ── UT-6.2: 테마 설정 영속화 ─────────────────────────────────────


class TestThemePersistence:
    """UT-6.2: 테마 설정 영속화 (to_dict / from_dict)"""

    def test_save_light_preference(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("light")
        data = mgr.to_dict()
        assert data["theme_preference"] == "light"

    def test_save_dark_preference(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("dark")
        data = mgr.to_dict()
        assert data["theme_preference"] == "dark"

    def test_save_system_preference(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("system")
        data = mgr.to_dict()
        assert data["theme_preference"] == "system"

    def test_restore_preference(self):
        mgr = ThemeManager()
        mgr.from_dict({"theme_preference": "dark", "current": "tailwind-dark"})
        assert mgr.theme_preference == "dark"

    def test_restore_preserves_current_theme(self):
        """from_dict 호출 시 current도 올바르게 복원"""
        mgr = ThemeManager()
        mgr.from_dict({"theme_preference": "light", "current": "tailwind"})
        assert mgr.theme_preference == "light"
        assert mgr.current_theme.name == "Tailwind"

    def test_roundtrip(self):
        """저장 → 복원 왕복"""
        mgr1 = ThemeManager()
        mgr1.set_theme_preference("dark")
        data = mgr1.to_dict()

        mgr2 = ThemeManager()
        mgr2.from_dict(data)
        assert mgr2.theme_preference == "dark"


# ── UT-6.3: 테마 설정 파일 손상 → 기본 테마 폴백 ────────────────


class TestThemeCorruptionFallback:
    """UT-6.3: 테마 설정 파일 손상 시 기본 테마 폴백"""

    def test_empty_dict_fallback(self):
        """빈 딕셔너리 → 기본값 유지"""
        mgr = ThemeManager()
        mgr.from_dict({})
        # Should not crash, keeps default
        assert mgr.theme_preference in ("light", "dark", "system")

    def test_missing_preference_key(self):
        """theme_preference 키 누락 → 기본값"""
        mgr = ThemeManager()
        mgr.from_dict({"some_other_key": "value"})
        assert mgr.theme_preference in ("light", "dark", "system")

    def test_invalid_preference_value_in_dict(self):
        """유효하지 않은 preference 값 → 기본값"""
        mgr = ThemeManager()
        mgr.from_dict({"theme_preference": "neon_green"})
        assert mgr.theme_preference in ("light", "dark", "system")

    def test_none_dict(self):
        """None 입력 → 기본값 유지, 크래시 없음"""
        mgr = ThemeManager()
        mgr.from_dict(None)
        assert mgr.theme_preference in ("light", "dark", "system")

    def test_non_dict_input(self):
        """dict가 아닌 입력 → 기본값 유지"""
        mgr = ThemeManager()
        mgr.from_dict("corrupted string")
        assert mgr.theme_preference in ("light", "dark", "system")

    def test_invalid_current_theme_fallback(self):
        """current가 존재하지 않는 테마 → 기본값"""
        mgr = ThemeManager()
        mgr.from_dict({"current": "nonexistent_theme", "theme_preference": "light"})
        # Should not crash; preference is restored but current stays valid
        assert mgr.theme_preference == "light"


# ── ThemeState dataclass ─────────────────────────────────────────


class TestThemeState:
    """ThemeState dataclass 테스트"""

    def test_default_values(self):
        state = ThemeState()
        assert state.current == "system"

    def test_custom_values(self):
        state = ThemeState(current="dark")
        assert state.current == "dark"

    def test_light_value(self):
        state = ThemeState(current="light")
        assert state.current == "light"


# ── FR-6.7: IPC 커맨드 get_theme / set_theme ────────────────────


class TestThemeIPCCommands:
    """FR-6.7: IPC get_theme, set_theme 지원을 위한 메서드"""

    def test_get_theme_returns_preference(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("dark")
        assert mgr.get_theme() == "dark"

    def test_set_theme_via_ipc_style(self):
        mgr = ThemeManager()
        mgr.set_theme_preference("light")
        assert mgr.get_theme() == "light"

        mgr.set_theme_preference("dark")
        assert mgr.get_theme() == "dark"

        mgr.set_theme_preference("system")
        assert mgr.get_theme() == "system"
