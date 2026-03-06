"""
Keyboard Shortcuts Manager
"""

from typing import Dict, List, Optional, Callable, Union
from dataclasses import dataclass
from enum import Enum

from PySide6.QtGui import QKeySequence


class ShortcutCategory(Enum):
    """단축키 카테고리"""

    FILE = "File"
    EDIT = "Edit"
    VIEW = "View"
    GRAPH = "Graph"
    DATA = "Data"
    HELP = "Help"


@dataclass
class Shortcut:
    """단축키 정의"""

    id: str
    name: str
    keys: Union[str, QKeySequence, QKeySequence.StandardKey]
    category: ShortcutCategory
    description: str = ""
    callback: Optional[Callable] = None
    enabled: bool = True
    default_keys: Union[str, QKeySequence, QKeySequence.StandardKey] = None

    def __post_init__(self):
        # 기본값 저장
        if self.default_keys is None:
            self.default_keys = self.keys

        # 키 변환은 lazy하게 수행
        self._convert_keys()

    def _convert_keys(self):
        """키 변환"""
        try:
            if isinstance(self.keys, str):
                self.keys = QKeySequence(self.keys)
            elif isinstance(self.keys, QKeySequence.StandardKey):
                self.keys = QKeySequence(self.keys)
        except Exception:
            # QApplication 없을 때 실패할 수 있음
            pass

    def reset(self):
        """기본값으로 초기화"""
        self.keys = self.default_keys
        self._convert_keys()


class ShortcutManager:
    """단축키 매니저"""

    def __init__(self):
        self._shortcuts: Dict[str, Shortcut] = {}
        self._customized: Dict[str, str] = {}

    def register(
        self,
        id: str,
        name: str,
        keys: Union[str, QKeySequence, QKeySequence.StandardKey],
        category: ShortcutCategory,
        description: str = "",
        callback: Optional[Callable] = None,
    ) -> Shortcut:
        """단축키 등록"""
        shortcut = Shortcut(
            id=id,
            name=name,
            keys=keys,
            category=category,
            description=description,
            callback=callback,
        )
        self._shortcuts[id] = shortcut
        return shortcut

    def get(self, id: str) -> Optional[Shortcut]:
        """단축키 조회"""
        return self._shortcuts.get(id)

    def list_all(self) -> List[Shortcut]:
        """전체 단축키 목록"""
        return list(self._shortcuts.values())

    def list_by_category(self, category: ShortcutCategory) -> List[Shortcut]:
        """카테고리별 단축키 목록"""
        return [s for s in self._shortcuts.values() if s.category == category]

    def connect(self, id: str, callback: Callable):
        """콜백 연결"""
        if id in self._shortcuts:
            self._shortcuts[id].callback = callback

    def disconnect(self, id: str):
        """콜백 연결 해제"""
        if id in self._shortcuts:
            self._shortcuts[id].callback = None

    def trigger(self, id: str):
        """단축키 트리거"""
        shortcut = self._shortcuts.get(id)
        if shortcut and shortcut.callback and shortcut.enabled:
            shortcut.callback()

    def set_keys(self, id: str, keys: Union[str, QKeySequence]):
        """단축키 변경"""
        if id in self._shortcuts:
            if isinstance(keys, str):
                keys = QKeySequence(keys)
            self._shortcuts[id].keys = keys
            self._customized[id] = keys.toString(QKeySequence.PortableText)

    def reset(self, id: str):
        """단축키 초기화"""
        if id in self._shortcuts:
            self._shortcuts[id].reset()
            if id in self._customized:
                del self._customized[id]

    def reset_all(self):
        """전체 초기화"""
        for shortcut in self._shortcuts.values():
            shortcut.reset()
        self._customized.clear()

    def check_conflict(self, keys: Union[str, QKeySequence]) -> Optional[Shortcut]:
        """충돌 확인"""
        if isinstance(keys, str):
            keys = QKeySequence(keys)

        keys_str = keys.toString()

        for shortcut in self._shortcuts.values():
            if shortcut.keys.toString() == keys_str:
                return shortcut

        return None

    def register_defaults(self):
        """기본 단축키 등록"""
        # File
        self.register(
            "file.open",
            "Open File",
            QKeySequence.StandardKey.Open,
            ShortcutCategory.FILE,
        )
        self.register(
            "file.save",
            "Save Project",
            QKeySequence.StandardKey.Save,
            ShortcutCategory.FILE,
        )
        self.register(
            "file.save_as",
            "Save As",
            QKeySequence.StandardKey.SaveAs,
            ShortcutCategory.FILE,
        )
        self.register(
            "file.close", "Close", QKeySequence.StandardKey.Close, ShortcutCategory.FILE
        )
        self.register(
            "file.quit", "Quit", QKeySequence.StandardKey.Quit, ShortcutCategory.FILE
        )

        # Edit
        self.register(
            "edit.undo", "Undo", QKeySequence.StandardKey.Undo, ShortcutCategory.EDIT
        )
        self.register(
            "edit.redo", "Redo", QKeySequence.StandardKey.Redo, ShortcutCategory.EDIT
        )
        self.register(
            "edit.cut", "Cut", QKeySequence.StandardKey.Cut, ShortcutCategory.EDIT
        )
        self.register(
            "edit.copy", "Copy", QKeySequence.StandardKey.Copy, ShortcutCategory.EDIT
        )
        self.register(
            "edit.paste", "Paste", QKeySequence.StandardKey.Paste, ShortcutCategory.EDIT
        )
        self.register(
            "edit.select_all",
            "Select All",
            QKeySequence.StandardKey.SelectAll,
            ShortcutCategory.EDIT,
        )
        self.register("edit.deselect", "Deselect", "Escape", ShortcutCategory.EDIT)
        self.register(
            "edit.delete",
            "Delete",
            QKeySequence.StandardKey.Delete,
            ShortcutCategory.EDIT,
        )

        # View
        self.register(
            "view.zoom_in",
            "Zoom In",
            QKeySequence.StandardKey.ZoomIn,
            ShortcutCategory.VIEW,
        )
        self.register(
            "view.zoom_out",
            "Zoom Out",
            QKeySequence.StandardKey.ZoomOut,
            ShortcutCategory.VIEW,
        )
        self.register("view.reset", "Reset View", "Home", ShortcutCategory.VIEW)
        self.register("view.autofit", "Autofit", "F", ShortcutCategory.VIEW)
        self.register(
            "view.fullscreen",
            "Fullscreen",
            QKeySequence.StandardKey.FullScreen,
            ShortcutCategory.VIEW,
        )

        # Graph
        self.register("graph.pan", "Pan Mode", "H", ShortcutCategory.GRAPH)
        self.register("graph.zoom", "Zoom Mode", "Z", ShortcutCategory.GRAPH)
        self.register("graph.rect_select", "Rect Select", "R", ShortcutCategory.GRAPH)
        self.register("graph.lasso_select", "Lasso Select", "L", ShortcutCategory.GRAPH)

        # Data
        self.register(
            "data.refresh",
            "Refresh Data",
            QKeySequence.StandardKey.Refresh,
            ShortcutCategory.DATA,
        )
        self.register("data.filter", "Filter", "Ctrl+F", ShortcutCategory.DATA)
        self.register("data.sort", "Sort", "Ctrl+Shift+S", ShortcutCategory.DATA)

        # Help
        self.register(
            "help.shortcuts", "Keyboard Shortcuts", "Ctrl+/", ShortcutCategory.HELP
        )
        self.register("help.about", "About", "", ShortcutCategory.HELP)

    def to_dict(self) -> Dict:
        """딕셔너리로 변환"""
        return {
            "customized": self._customized.copy(),
        }

    def from_dict(self, data: Dict):
        """딕셔너리에서 복원"""
        if "customized" in data:
            for id, keys in data["customized"].items():
                if id in self._shortcuts:
                    self.set_keys(id, keys)

    def get_help_text(self) -> str:
        """도움말 텍스트 생성"""
        lines = []

        for category in ShortcutCategory:
            shortcuts = self.list_by_category(category)
            if shortcuts:
                lines.append(f"\n{category.value}:")
                for s in shortcuts:
                    keys_str = (
                        s.keys.toString()
                        if isinstance(s.keys, QKeySequence)
                        else str(s.keys)
                    )
                    lines.append(f"  {keys_str}: {s.name}")

        return "\n".join(lines)

    def get_cheatsheet(self) -> Dict[str, List[Dict]]:
        """치트시트 생성"""
        result = {}

        for category in ShortcutCategory:
            shortcuts = self.list_by_category(category)
            if shortcuts:
                result[category.value] = [
                    {
                        "keys": s.keys.toString()
                        if isinstance(s.keys, QKeySequence)
                        else str(s.keys),
                        "name": s.name,
                        "description": s.description,
                    }
                    for s in shortcuts
                ]

        return result
