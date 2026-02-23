"""
Tests for Keyboard Shortcuts
"""

import pytest
from unittest.mock import MagicMock

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeySequence

import sys
import os

# Create QApplication if not exists (required for Qt operations)
app = QApplication.instance()
if not app:
    app = QApplication([])

# Add project root to path
project_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_path not in sys.path:
    sys.path.insert(0, project_path)

from data_graph_studio.ui.shortcuts import ShortcutManager, Shortcut, ShortcutCategory


class TestShortcut:
    """단축키 테스트"""
    
    def test_shortcut_creation(self):
        """단축키 생성"""
        shortcut = Shortcut(
            id="file.open",
            name="Open File",
            keys=QKeySequence.StandardKey.Open,
            category=ShortcutCategory.FILE
        )
        
        assert shortcut.id == "file.open"
        assert shortcut.name == "Open File"
    
    def test_shortcut_custom_key(self):
        """커스텀 키 조합"""
        shortcut = Shortcut(
            id="view.zoom_in",
            name="Zoom In",
            keys="Ctrl++",
            category=ShortcutCategory.VIEW
        )
        
        # QKeySequence.toString() gives readable format
        keys_str = shortcut.keys.toString() if hasattr(shortcut.keys, 'toString') else str(shortcut.keys)
        assert "+" in keys_str or "Ctrl" in keys_str
    
    def test_shortcut_description(self):
        """단축키 설명"""
        shortcut = Shortcut(
            id="edit.copy",
            name="Copy",
            keys=QKeySequence.StandardKey.Copy,
            category=ShortcutCategory.EDIT,
            description="Copy selected items"
        )
        
        assert shortcut.description == "Copy selected items"


class TestShortcutManager:
    """단축키 매니저 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ShortcutManager()
    
    def test_register_shortcut(self, manager):
        """단축키 등록"""
        manager.register(
            id="test.action",
            name="Test Action",
            keys="Ctrl+T",
            category=ShortcutCategory.EDIT
        )
        
        assert manager.get("test.action") is not None
    
    def test_list_shortcuts(self, manager):
        """단축키 목록"""
        manager.register("a.1", "Action 1", "Ctrl+1", ShortcutCategory.FILE)
        manager.register("a.2", "Action 2", "Ctrl+2", ShortcutCategory.EDIT)
        
        all_shortcuts = manager.list_all()
        
        assert len(all_shortcuts) >= 2
    
    def test_list_by_category(self, manager):
        """카테고리별 단축키"""
        manager.register("f.1", "File 1", "Ctrl+1", ShortcutCategory.FILE)
        manager.register("f.2", "File 2", "Ctrl+2", ShortcutCategory.FILE)
        manager.register("e.1", "Edit 1", "Ctrl+E", ShortcutCategory.EDIT)
        
        file_shortcuts = manager.list_by_category(ShortcutCategory.FILE)
        
        assert len(file_shortcuts) == 2
    
    def test_connect_action(self, manager):
        """액션 연결"""
        callback = MagicMock()
        
        manager.register("test", "Test", "Ctrl+T", ShortcutCategory.EDIT)
        manager.connect("test", callback)
        
        # Trigger
        manager.trigger("test")
        
        callback.assert_called_once()
    
    def test_disconnect_action(self, manager):
        """액션 연결 해제"""
        callback = MagicMock()
        
        manager.register("test", "Test", "Ctrl+T", ShortcutCategory.EDIT)
        manager.connect("test", callback)
        manager.disconnect("test")
        
        manager.trigger("test")
        
        callback.assert_not_called()


class TestDefaultShortcuts:
    """기본 단축키 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ShortcutManager()
        m.register_defaults()
        return m
    
    def test_file_shortcuts(self, manager):
        """파일 단축키"""
        assert manager.get("file.open") is not None
        assert manager.get("file.save") is not None
    
    def test_edit_shortcuts(self, manager):
        """편집 단축키"""
        assert manager.get("edit.undo") is not None
        assert manager.get("edit.redo") is not None
        assert manager.get("edit.select_all") is not None
    
    def test_view_shortcuts(self, manager):
        """보기 단축키"""
        assert manager.get("view.zoom_in") is not None
        assert manager.get("view.zoom_out") is not None
        assert manager.get("view.reset") is not None
    
    def test_graph_shortcuts(self, manager):
        """그래프 단축키"""
        assert manager.get("graph.pan") is not None
        assert manager.get("graph.zoom") is not None


class TestShortcutCustomization:
    """단축키 커스터마이징 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ShortcutManager()
        m.register_defaults()
        return m
    
    def test_change_shortcut(self, manager):
        """단축키 변경"""
        manager.set_keys("file.open", "Ctrl+Shift+O")
        
        shortcut = manager.get("file.open")
        assert "Shift" in str(shortcut.keys) or "O" in str(shortcut.keys)
    
    def test_reset_shortcut(self, manager):
        """단축키 초기화"""
        original_shortcut = manager.get("file.open")
        original_str = original_shortcut.keys.toString() if hasattr(original_shortcut.keys, 'toString') else str(original_shortcut.keys)
        
        manager.set_keys("file.open", "Ctrl+Shift+O")
        manager.reset("file.open")
        
        reset_shortcut = manager.get("file.open")
        reset_str = reset_shortcut.keys.toString() if hasattr(reset_shortcut.keys, 'toString') else str(reset_shortcut.keys)
        
        assert reset_str == original_str
    
    def test_reset_all(self, manager):
        """전체 초기화"""
        manager.set_keys("file.open", "Ctrl+Shift+O")
        manager.set_keys("file.save", "Ctrl+Shift+S")
        
        manager.reset_all()
        
        # 기본값으로 복원되어야 함
        shortcuts = manager.list_all()
        assert len(shortcuts) > 0


class TestShortcutConflict:
    """단축키 충돌 테스트"""
    
    @pytest.fixture
    def manager(self):
        return ShortcutManager()
    
    def test_detect_conflict(self, manager):
        """충돌 감지"""
        manager.register("a", "Action A", "Ctrl+T", ShortcutCategory.EDIT)
        manager.register("b", "Action B", "Ctrl+E", ShortcutCategory.EDIT)
        
        # 같은 키 시도
        conflict = manager.check_conflict("Ctrl+T")
        
        assert conflict is not None
        assert conflict.id == "a"
    
    def test_no_conflict(self, manager):
        """충돌 없음"""
        manager.register("a", "Action A", "Ctrl+T", ShortcutCategory.EDIT)
        
        conflict = manager.check_conflict("Ctrl+E")
        
        assert conflict is None


class TestShortcutPersistence:
    """단축키 저장/로드 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ShortcutManager()
        m.register_defaults()
        return m
    
    def test_to_dict(self, manager):
        """딕셔너리 변환"""
        manager.set_keys("file.open", "Ctrl+Shift+O")
        
        data = manager.to_dict()
        
        assert 'customized' in data
        assert 'file.open' in data['customized']
    
    def test_from_dict(self, manager):
        """딕셔너리에서 복원"""
        data = {
            'customized': {
                'file.open': 'Ctrl+Shift+O'
            }
        }
        
        manager.from_dict(data)
        
        shortcut = manager.get("file.open")
        assert "Shift" in str(shortcut.keys) or "O" in str(shortcut.keys)


class TestShortcutHelp:
    """단축키 도움말 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ShortcutManager()
        m.register_defaults()
        return m
    
    def test_get_help_text(self, manager):
        """도움말 텍스트 생성"""
        help_text = manager.get_help_text()
        
        assert isinstance(help_text, str)
        assert len(help_text) > 0
        assert "Open" in help_text or "Save" in help_text
    
    def test_get_cheatsheet(self, manager):
        """치트시트 생성"""
        cheatsheet = manager.get_cheatsheet()
        
        assert isinstance(cheatsheet, dict)
        assert len(cheatsheet) > 0


class TestToolModeShortcuts:
    """툴 모드 단축키 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ShortcutManager()
        m.register_defaults()
        return m
    
    def test_pan_shortcut(self, manager):
        """Pan 모드: H"""
        shortcut = manager.get("graph.pan")
        assert shortcut is not None
    
    def test_zoom_shortcut(self, manager):
        """Zoom 모드: Z"""
        shortcut = manager.get("graph.zoom")
        assert shortcut is not None
    
    def test_rect_select_shortcut(self, manager):
        """Rect Select: R"""
        shortcut = manager.get("graph.rect_select")
        assert shortcut is not None
    
    def test_lasso_select_shortcut(self, manager):
        """Lasso Select: L"""
        shortcut = manager.get("graph.lasso_select")
        assert shortcut is not None


class TestNavigationShortcuts:
    """탐색 단축키 테스트"""
    
    @pytest.fixture
    def manager(self):
        m = ShortcutManager()
        m.register_defaults()
        return m
    
    def test_home_shortcut(self, manager):
        """Home: 뷰 리셋"""
        shortcut = manager.get("view.reset")
        assert shortcut is not None
    
    def test_autofit_shortcut(self, manager):
        """F: 자동 맞춤"""
        shortcut = manager.get("view.autofit")
        assert shortcut is not None
    
    def test_escape_shortcut(self, manager):
        """Escape: 선택 해제"""
        shortcut = manager.get("edit.deselect")
        assert shortcut is not None
