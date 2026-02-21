"""
Property Panel - Spotfire 스타일 속성 패널

시각화 속성을 편집하는 UI 컴포넌트입니다.
"""

from typing import List, Dict, Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

try:
    from PySide6.QtCore import Qt, Signal
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,  # noqa: F401
        QFrame, QPushButton, QLineEdit, QCheckBox, QSpinBox,  # noqa: F401
        QDoubleSpinBox, QComboBox, QColorDialog, QFontDialog,  # noqa: F401
        QGroupBox, QToolButton, QTreeWidget, QTreeWidgetItem,  # noqa: F401
        QSizePolicy  # noqa: F401
    )
    from PySide6.QtGui import QColor, QFont
    HAS_QT = True
except ImportError:
    HAS_QT = False
    class Signal:
        def __init__(self, *args):
            pass


class PropertyType(Enum):
    """속성 타입"""
    STRING = "string"
    NUMBER = "number"
    INTEGER = "integer"
    BOOLEAN = "boolean"
    COLOR = "color"
    FONT = "font"
    ENUM = "enum"
    LIST = "list"
    COLUMN = "column"


@dataclass
class PropertyItem:
    """속성 항목"""
    name: str
    display_name: str
    property_type: PropertyType
    value: Any = None
    default_value: Any = None
    description: str = ""

    # 타입별 옵션
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    enum_values: List[str] = field(default_factory=list)
    columns: List[str] = field(default_factory=list)

    # 콜백
    on_change: Optional[Callable[[Any], None]] = None


@dataclass
class PropertyGroup:
    """속성 그룹"""
    name: str
    display_name: str = ""
    expanded: bool = True
    items: Dict[str, PropertyItem] = field(default_factory=dict)

    def __post_init__(self):
        if not self.display_name:
            self.display_name = self.name


class PropertyPanel:
    """
    속성 패널

    시각화 속성을 편집하는 패널입니다.
    """

    def __init__(self):
        self._groups: Dict[str, PropertyGroup] = {}
        self._widget = None

    def add_group(self, group: PropertyGroup) -> None:
        """그룹 추가"""
        self._groups[group.name] = group

    def remove_group(self, name: str) -> None:
        """그룹 제거"""
        if name in self._groups:
            del self._groups[name]

    def get_group_names(self) -> List[str]:
        """그룹 이름 목록"""
        return list(self._groups.keys())

    def add_item(self, group_name: str, item: PropertyItem) -> None:
        """항목 추가"""
        if group_name in self._groups:
            self._groups[group_name].items[item.name] = item

    def remove_item(self, group_name: str, item_name: str) -> None:
        """항목 제거"""
        if group_name in self._groups:
            if item_name in self._groups[group_name].items:
                del self._groups[group_name].items[item_name]

    def get_value(self, group_name: str, item_name: str) -> Any:
        """값 조회"""
        if group_name in self._groups:
            if item_name in self._groups[group_name].items:
                return self._groups[group_name].items[item_name].value
        return None

    def set_value(self, group_name: str, item_name: str, value: Any) -> None:
        """값 설정"""
        if group_name in self._groups:
            if item_name in self._groups[group_name].items:
                item = self._groups[group_name].items[item_name]
                item.value = value
                if item.on_change:
                    item.on_change(value)

    def get_all_values(self) -> Dict[str, Dict[str, Any]]:
        """모든 값 조회"""
        result = {}
        for group_name, group in self._groups.items():
            result[group_name] = {}
            for item_name, item in group.items.items():
                result[group_name][item_name] = item.value
        return result

    def set_all_values(self, values: Dict[str, Dict[str, Any]]) -> None:
        """모든 값 설정"""
        for group_name, group_values in values.items():
            for item_name, value in group_values.items():
                self.set_value(group_name, item_name, value)

    def reset_to_defaults(self) -> None:
        """기본값으로 리셋"""
        for group in self._groups.values():
            for item in group.items.values():
                if item.default_value is not None:
                    item.value = item.default_value


class ColorPickerWidget:
    """
    색상 선택 위젯
    """

    def __init__(self, initial_color: str = "#000000"):
        self._color = initial_color

    def get_color(self) -> str:
        """색상 반환"""
        return self._color

    def set_color(self, color: str) -> None:
        """색상 설정"""
        self._color = color

    def show_picker(self) -> Optional[str]:
        """색상 선택 다이얼로그"""
        if HAS_QT:
            color = QColorDialog.getColor(QColor(self._color))
            if color.isValid():
                self._color = color.name()
                return self._color
        return None


class FontPickerWidget:
    """
    폰트 선택 위젯
    """

    def __init__(
        self,
        family: str = "Arial",
        size: int = 10,
        bold: bool = False,
        italic: bool = False
    ):
        self._family = family
        self._size = size
        self._bold = bold
        self._italic = italic

    def get_font(self) -> Dict[str, Any]:
        """폰트 정보 반환"""
        return {
            "family": self._family,
            "size": self._size,
            "bold": self._bold,
            "italic": self._italic
        }

    def set_font(
        self,
        family: Optional[str] = None,
        size: Optional[int] = None,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None
    ) -> None:
        """폰트 설정"""
        if family is not None:
            self._family = family
        if size is not None:
            self._size = size
        if bold is not None:
            self._bold = bold
        if italic is not None:
            self._italic = italic

    def show_picker(self) -> Optional[Dict[str, Any]]:
        """폰트 선택 다이얼로그"""
        if HAS_QT:
            font = QFont(self._family, self._size)
            font.setBold(self._bold)
            font.setItalic(self._italic)

            ok, new_font = QFontDialog.getFont(font)
            if ok:
                self._family = new_font.family()
                self._size = new_font.pointSize()
                self._bold = new_font.bold()
                self._italic = new_font.italic()
                return self.get_font()
        return None


if HAS_QT:
    class PropertyPanelWidget(QWidget):
        """
        속성 패널 위젯

        속성을 편집하는 트리 형태의 UI입니다.
        """

        property_changed = Signal(str, str, object)  # group, item, value

        def __init__(self, parent=None):
            super().__init__(parent)

            self._model = PropertyPanel()
            self._setup_ui()

        def _setup_ui(self) -> None:
            """UI 설정"""
            layout = QVBoxLayout(self)
            layout.setContentsMargins(0, 0, 0, 0)

            # 헤더
            header = QFrame()
            header_layout = QHBoxLayout(header)
            header_layout.setContentsMargins(8, 4, 8, 4)

            title = QLabel("Properties")
            title.setStyleSheet("font-weight: bold;")
            header_layout.addWidget(title)

            header_layout.addStretch()

            reset_btn = QPushButton("Reset")
            reset_btn.setToolTip("Reset all properties to default values")
            reset_btn.clicked.connect(self._reset_to_defaults)
            header_layout.addWidget(reset_btn)

            layout.addWidget(header)

            # 트리 위젯
            self._tree = QTreeWidget()
            self._tree.setHeaderLabels(["Property", "Value"])
            self._tree.setColumnWidth(0, 150)
            self._tree.itemChanged.connect(self._on_item_changed)

            layout.addWidget(self._tree)

        def set_model(self, model: PropertyPanel) -> None:
            """모델 설정"""
            self._model = model
            self._build_tree()

        def _build_tree(self) -> None:
            """트리 구성"""
            self._tree.clear()

            for group_name, group in self._model._groups.items():
                group_item = QTreeWidgetItem([group.display_name])
                group_item.setExpanded(group.expanded)
                self._tree.addTopLevelItem(group_item)

                for item_name, prop in group.items.items():
                    prop_item = QTreeWidgetItem([prop.display_name])
                    prop_item.setData(0, Qt.ItemDataRole.UserRole, (group_name, item_name))

                    # 값 위젯 생성 (간소화)
                    if prop.property_type == PropertyType.BOOLEAN:
                        prop_item.setCheckState(1, Qt.CheckState.Checked if prop.value else Qt.CheckState.Unchecked)
                    else:
                        prop_item.setText(1, str(prop.value) if prop.value is not None else "")

                    group_item.addChild(prop_item)

        def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
            """항목 변경 이벤트"""
            if column != 1:
                return

            data = item.data(0, Qt.ItemDataRole.UserRole)
            if data is None:
                return

            group_name, item_name = data

            # 값 추출
            prop = self._model._groups[group_name].items[item_name]

            if prop.property_type == PropertyType.BOOLEAN:
                value = item.checkState(1) == Qt.CheckState.Checked
            else:
                value = item.text(1)

            self._model.set_value(group_name, item_name, value)
            self.property_changed.emit(group_name, item_name, value)

        def _reset_to_defaults(self) -> None:
            """기본값으로 리셋"""
            self._model.reset_to_defaults()
            self._build_tree()
