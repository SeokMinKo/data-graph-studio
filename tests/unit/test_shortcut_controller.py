"""
Tests for ShortcutController (Feature 7: Keyboard Shortcuts)

TDD tests covering:
- UT-7.1: ShortcutConfig 로드/저장
- UT-7.2: 단축키 충돌 감지
- UT-7.3: 단축키 커스터마이징 (키 변경)
- UT-7.4: macOS 시스템 단축키 충돌 경고
"""

import json
import os
import sys
import pytest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])

# Add project root to path
project_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from data_graph_studio.ui.shortcuts import ShortcutManager
from data_graph_studio.ui.controllers.shortcut_controller import ShortcutController


class TestShortcutConfigLoadSave:
    """UT-7.1: ShortcutConfig 로드/저장"""

    @pytest.fixture
    def tmp_config_path(self, tmp_path):
        return str(tmp_path / "shortcuts.json")

    @pytest.fixture
    def controller(self, tmp_config_path):
        ctrl = ShortcutController(config_path=tmp_config_path)
        ctrl.register_defaults()
        return ctrl

    def test_save_config_creates_file(self, controller, tmp_config_path):
        """설정 저장 시 JSON 파일 생성"""
        controller.save_config()
        assert os.path.exists(tmp_config_path)

    def test_save_and_load_round_trip(self, controller, tmp_config_path):
        """저장 후 로드하면 같은 커스텀 키 복원"""
        controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        controller.save_config()

        # 새 컨트롤러로 로드
        ctrl2 = ShortcutController(config_path=tmp_config_path)
        ctrl2.register_defaults()
        ctrl2.load_config()

        shortcut = ctrl2.get_shortcut("file.open")
        assert shortcut is not None
        keys_str = shortcut.keys.toString()
        assert "Shift" in keys_str

    def test_load_nonexistent_file_uses_defaults(self, tmp_path):
        """존재하지 않는 설정 파일 → 기본값 사용"""
        nonexistent = str(tmp_path / "nonexistent.json")
        ctrl = ShortcutController(config_path=nonexistent)
        ctrl.register_defaults()
        ctrl.load_config()

        # 기본 단축키가 있어야 함
        assert ctrl.get_shortcut("file.open") is not None

    def test_load_corrupted_file_resets_to_defaults(self, tmp_config_path):
        """ERR-7.2: 손상된 설정 파일 → 기본값 복원 + 알림"""
        # 손상된 JSON 파일 생성
        with open(tmp_config_path, "w") as f:
            f.write("{invalid json content!!!")

        ctrl = ShortcutController(config_path=tmp_config_path)
        ctrl.register_defaults()
        result = ctrl.load_config()

        assert result is False  # 로드 실패
        # 기본 단축키가 여전히 동작해야 함
        assert ctrl.get_shortcut("file.open") is not None

    def test_save_only_customized_shortcuts(self, controller, tmp_config_path):
        """커스터마이즈된 단축키만 저장"""
        controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        controller.save_config()

        with open(tmp_config_path, "r") as f:
            data = json.load(f)

        assert "customized" in data
        assert "file.open" in data["customized"]
        # 변경하지 않은 단축키는 저장되지 않아야 함
        assert "file.save" not in data.get("customized", {})


class TestShortcutConflictDetection:
    """UT-7.2: 단축키 충돌 감지"""

    @pytest.fixture
    def controller(self, tmp_path):
        ctrl = ShortcutController(config_path=str(tmp_path / "shortcuts.json"))
        ctrl.register_defaults()
        return ctrl

    def test_detect_conflict_with_existing_shortcut(self, controller):
        """기존 단축키와 충돌 감지"""
        # file.open은 Cmd+O (Ctrl+O)
        conflict = controller.check_conflict("Ctrl+O")
        assert conflict is not None

    def test_detect_conflict_when_changing_shortcut(self, controller):
        """단축키 변경 시 충돌 감지 (자기 자신 제외)"""
        # file.save의 키를 file.open의 키로 변경 시도
        conflict = controller.check_conflict_for("file.save", "Ctrl+O")
        assert conflict is not None
        assert conflict.id == "file.open"

    def test_no_conflict_with_self(self, controller):
        """같은 단축키 ID에 대해서는 충돌 아님"""
        # file.open의 현재 키 조합으로 자기 자신 체크
        open_shortcut = controller.get_shortcut("file.open")
        keys_str = open_shortcut.keys.toString()
        conflict = controller.check_conflict_for("file.open", keys_str)
        assert conflict is None

    def test_no_conflict_with_unused_key(self, controller):
        """사용하지 않는 키 조합은 충돌 없음"""
        conflict = controller.check_conflict("Ctrl+Alt+Shift+F12")
        assert conflict is None

    def test_conflict_after_customization(self, controller):
        """커스터마이징 후 충돌 감지"""
        # file.open을 Ctrl+Shift+O로 변경
        controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        # 이제 Ctrl+Shift+O가 충돌
        conflict = controller.check_conflict("Ctrl+Shift+O")
        assert conflict is not None
        assert conflict.id == "file.open"


class TestShortcutCustomization:
    """UT-7.3: 단축키 커스터마이징 (키 변경)"""

    @pytest.fixture
    def controller(self, tmp_path):
        ctrl = ShortcutController(config_path=str(tmp_path / "shortcuts.json"))
        ctrl.register_defaults()
        return ctrl

    def test_change_shortcut_key(self, controller):
        """단축키 키 조합 변경"""
        controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        shortcut = controller.get_shortcut("file.open")
        assert "Shift" in shortcut.keys.toString()

    def test_reset_single_shortcut(self, controller):
        """단일 단축키 초기화"""
        original = controller.get_shortcut("file.open")
        original_keys = original.keys.toString()

        controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        controller.reset_shortcut("file.open")

        restored = controller.get_shortcut("file.open")
        assert restored.keys.toString() == original_keys

    def test_reset_all_shortcuts(self, controller):
        """전체 단축키 초기화"""
        controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        controller.set_custom_keys("file.save", "Ctrl+Shift+X")
        controller.reset_all()

        # 커스텀 설정이 비어있어야 함
        assert len(controller.get_customized()) == 0

    def test_get_all_shortcuts_by_category(self, controller):
        """카테고리별 단축키 조회"""
        categories = controller.get_shortcuts_by_category()
        assert len(categories) > 0
        # 각 카테고리에 단축키가 있어야 함
        for category, shortcuts in categories.items():
            assert len(shortcuts) > 0

    def test_invalid_key_combination_rejected(self, controller):
        """ERR-7.1: 빈 키 조합 거부"""
        result = controller.set_custom_keys("file.open", "")
        assert result is False
        # 이전 값이 유지되어야 함
        shortcut = controller.get_shortcut("file.open")
        assert shortcut.keys.toString() != ""

    def test_set_custom_keys_returns_true_on_success(self, controller):
        """유효한 키 변경 시 True 반환"""
        result = controller.set_custom_keys("file.open", "Ctrl+Shift+O")
        assert result is True


class TestMacOSSystemShortcutConflict:
    """UT-7.4: macOS 시스템 단축키 충돌 경고"""

    @pytest.fixture
    def controller(self, tmp_path):
        ctrl = ShortcutController(config_path=str(tmp_path / "shortcuts.json"))
        ctrl.register_defaults()
        return ctrl

    def test_detect_macos_system_conflict_cmd_h(self, controller):
        """Cmd+H (Hide) 시스템 단축키 충돌 감지"""
        assert controller.is_macos_system_shortcut("Meta+H")

    def test_detect_macos_system_conflict_cmd_m(self, controller):
        """Cmd+M (Minimize) 시스템 단축키 충돌 감지"""
        assert controller.is_macos_system_shortcut("Meta+M")

    def test_detect_macos_system_conflict_cmd_q(self, controller):
        """Cmd+Q (Quit) 시스템 단축키 충돌 감지"""
        assert controller.is_macos_system_shortcut("Meta+Q")

    def test_detect_macos_system_conflict_cmd_w(self, controller):
        """Cmd+W (Close Window) 시스템 단축키 충돌 감지"""
        assert controller.is_macos_system_shortcut("Meta+W")

    def test_detect_macos_system_conflict_cmd_d(self, controller):
        """Cmd+D (Dock/Desktop) 시스템 단축키 충돌 감지"""
        assert controller.is_macos_system_shortcut("Meta+D")

    def test_no_conflict_with_safe_key(self, controller):
        """안전한 키 조합은 충돌 아님"""
        assert not controller.is_macos_system_shortcut("Meta+Shift+D")

    def test_prd_changed_shortcuts_avoid_system_conflicts(self, controller):
        """PRD에서 변경된 단축키가 시스템 충돌 없음을 확인"""
        # Cmd+Shift+D (대시보드) - Cmd+D에서 변경됨
        dashboard = controller.get_shortcut("view.dashboard_toggle")
        if dashboard:
            assert not controller.is_macos_system_shortcut(dashboard.keys.toString())

        # Cmd+Shift+L (스트리밍) - Cmd+L에서 변경됨
        streaming = controller.get_shortcut("view.streaming_toggle")
        if streaming:
            assert not controller.is_macos_system_shortcut(streaming.keys.toString())

    def test_warn_on_customization_to_system_shortcut(self, controller):
        """커스터마이징 시 시스템 단축키 충돌 경고 목록 반환"""
        warnings = controller.get_conflict_warnings("file.open", "Meta+H")
        assert any("macOS system shortcut" in w for w in warnings)

    def test_no_warning_for_safe_customization(self, controller):
        """안전한 키 조합은 경고 없음"""
        warnings = controller.get_conflict_warnings("file.open", "Ctrl+Shift+F12")
        assert len(warnings) == 0


class TestDefaultShortcutMappings:
    """PRD FR-7.1에 정의된 기본 단축키 매핑 테스트"""

    @pytest.fixture
    def controller(self, tmp_path):
        ctrl = ShortcutController(config_path=str(tmp_path / "shortcuts.json"))
        ctrl.register_defaults()
        return ctrl

    def test_file_open_shortcut(self, controller):
        """Cmd+O → 파일 열기"""
        shortcut = controller.get_shortcut("file.open")
        assert shortcut is not None

    def test_file_save_shortcut(self, controller):
        """Cmd+S → 프로파일 저장"""
        shortcut = controller.get_shortcut("file.save")
        assert shortcut is not None

    def test_file_save_as_shortcut(self, controller):
        """Cmd+Shift+S → 다른 이름으로 저장"""
        shortcut = controller.get_shortcut("file.save_as")
        assert shortcut is not None

    def test_export_shortcut(self, controller):
        """Cmd+E → 내보내기"""
        shortcut = controller.get_shortcut("file.export")
        assert shortcut is not None

    def test_dashboard_toggle_shortcut(self, controller):
        """Cmd+Shift+D → 대시보드 모드 토글 (Cmd+D에서 변경)"""
        shortcut = controller.get_shortcut("view.dashboard_toggle")
        assert shortcut is not None
        keys_str = shortcut.keys.toString()
        assert "Shift" in keys_str

    def test_streaming_toggle_shortcut(self, controller):
        """Cmd+Shift+L → 스트리밍 토글 (Cmd+L에서 변경)"""
        shortcut = controller.get_shortcut("view.streaming_toggle")
        assert shortcut is not None
        keys_str = shortcut.keys.toString()
        assert "Shift" in keys_str

    def test_theme_toggle_shortcut(self, controller):
        """Cmd+T → 테마 토글"""
        shortcut = controller.get_shortcut("view.theme_toggle")
        assert shortcut is not None

    def test_column_create_shortcut(self, controller):
        """Cmd+K → 컬럼 생성"""
        shortcut = controller.get_shortcut("data.column_create")
        assert shortcut is not None

    def test_annotation_mode_toggle(self, controller):
        """Cmd+Shift+A → 주석 모드 토글"""
        shortcut = controller.get_shortcut("edit.annotation_mode")
        assert shortcut is not None

    def test_annotation_panel_toggle(self, controller):
        """Cmd+Shift+B → 주석 패널 토글"""
        shortcut = controller.get_shortcut("view.annotation_panel")
        assert shortcut is not None

    def test_shortcut_help(self, controller):
        """Cmd+/ → 단축키 도움말"""
        shortcut = controller.get_shortcut("help.shortcuts")
        assert shortcut is not None

    def test_undo_shortcut(self, controller):
        """Cmd+Z → Undo"""
        shortcut = controller.get_shortcut("edit.undo")
        assert shortcut is not None

    def test_redo_shortcut(self, controller):
        """Cmd+Shift+Z → Redo"""
        shortcut = controller.get_shortcut("edit.redo")
        assert shortcut is not None

    def test_pan_mode_space(self, controller):
        """Space → 차트 팬 모드"""
        shortcut = controller.get_shortcut("graph.pan_space")
        assert shortcut is not None

    def test_fullscreen_f11(self, controller):
        """F11 → 전체 화면"""
        shortcut = controller.get_shortcut("view.fullscreen")
        assert shortcut is not None

    def test_dashboard_cell_focus_1_to_9(self, controller):
        """Cmd+1~9 → 대시보드 셀 포커스"""
        for i in range(1, 10):
            shortcut = controller.get_shortcut(f"dashboard.cell_{i}")
            assert shortcut is not None, f"dashboard.cell_{i} should exist"


class TestShortcutControllerIntegration:
    """ShortcutController의 ShortcutManager 래핑/확장 테스트"""

    @pytest.fixture
    def controller(self, tmp_path):
        ctrl = ShortcutController(config_path=str(tmp_path / "shortcuts.json"))
        ctrl.register_defaults()
        return ctrl

    def test_controller_wraps_manager(self, controller):
        """컨트롤러가 ShortcutManager를 내부에 포함"""
        assert controller.manager is not None
        assert isinstance(controller.manager, ShortcutManager)

    def test_controller_list_all(self, controller):
        """전체 단축키 목록 조회"""
        shortcuts = controller.list_all()
        assert len(shortcuts) > 0

    def test_controller_trigger(self, controller):
        """단축키 트리거"""
        callback = MagicMock()
        controller.connect("file.open", callback)
        controller.trigger("file.open")
        callback.assert_called_once()

    def test_get_cheatsheet(self, controller):
        """치트시트 생성"""
        cheatsheet = controller.get_cheatsheet()
        assert isinstance(cheatsheet, dict)
        assert len(cheatsheet) > 0
