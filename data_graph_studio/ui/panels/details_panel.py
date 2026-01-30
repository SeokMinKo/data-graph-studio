"""
Details-on-Demand Panel - Spotfire 스타일 상세 정보 패널

마킹된 데이터의 상세 정보를 테이블 형태로 표시합니다.
"""

from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex, Signal
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableView, QHeaderView,
    QLabel, QPushButton, QMenu, QFileDialog, QApplication,
    QFrame, QToolButton, QSizePolicy
)
from PySide6.QtGui import QAction, QClipboard
import polars as pl


@dataclass
class DetailsColumnConfig:
    """Details 컬럼 설정"""
    name: str
    display_name: Optional[str] = None
    visible: bool = True
    width: int = 100
    format_string: Optional[str] = None
    alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft

    def format_value(self, value: Any) -> str:
        """값 포맷팅"""
        if value is None:
            return ""

        if self.format_string:
            try:
                return self.format_string.format(value)
            except (ValueError, TypeError):
                return str(value)

        return str(value)


class DetailsOnDemandModel(QAbstractTableModel):
    """
    Details-on-Demand 테이블 모델

    마킹된 데이터만 표시하는 테이블 모델입니다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self._data: Optional[pl.DataFrame] = None
        self._marked_indices: Set[int] = set()
        self._display_data: Optional[pl.DataFrame] = None

        # 컬럼 설정
        self._column_configs: Dict[str, DetailsColumnConfig] = {}
        self._column_order: List[str] = []

    def set_data(self, data: pl.DataFrame) -> None:
        """데이터 설정"""
        self.beginResetModel()

        self._data = data
        self._column_order = list(data.columns)

        # 기본 컬럼 설정 생성
        self._column_configs = {
            col: DetailsColumnConfig(name=col, display_name=col)
            for col in data.columns
        }

        self._update_display_data()
        self.endResetModel()

    def set_marked_indices(self, indices: Set[int]) -> None:
        """마킹된 인덱스 설정"""
        self.beginResetModel()
        self._marked_indices = set(indices)
        self._update_display_data()
        self.endResetModel()

    def _update_display_data(self) -> None:
        """표시할 데이터 업데이트"""
        if self._data is None or not self._marked_indices:
            self._display_data = None
            return

        # 마킹된 행만 추출
        indices = sorted(self._marked_indices)
        valid_indices = [i for i in indices if 0 <= i < len(self._data)]

        if valid_indices:
            self._display_data = self._data[valid_indices]
        else:
            self._display_data = None

    def rowCount(self, parent=QModelIndex()) -> int:
        """행 수"""
        if self._display_data is None:
            return 0
        return len(self._display_data)

    def columnCount(self, parent=QModelIndex()) -> int:
        """열 수"""
        if self._data is None:
            return 0
        return len(self.get_visible_columns())

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        """셀 데이터"""
        if not index.isValid():
            return None

        if self._display_data is None:
            return None

        row = index.row()
        col_idx = index.column()

        visible_cols = self.get_visible_columns()
        if col_idx >= len(visible_cols):
            return None

        col_name = visible_cols[col_idx]

        if role == Qt.ItemDataRole.DisplayRole:
            value = self._display_data[row, col_name]
            config = self._column_configs.get(col_name)
            if config:
                return config.format_value(value)
            return str(value) if value is not None else ""

        elif role == Qt.ItemDataRole.TextAlignmentRole:
            config = self._column_configs.get(col_name)
            if config:
                return config.alignment
            return Qt.AlignmentFlag.AlignLeft

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        """헤더 데이터"""
        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Horizontal:
            visible_cols = self.get_visible_columns()
            if section < len(visible_cols):
                col_name = visible_cols[section]
                config = self._column_configs.get(col_name)
                if config and config.display_name:
                    return config.display_name
                return col_name

        elif orientation == Qt.Orientation.Vertical:
            return section + 1

        return None

    def get_visible_columns(self) -> List[str]:
        """가시적인 컬럼 목록"""
        return [
            col for col in self._column_order
            if col in self._column_configs
            and self._column_configs[col].visible
        ]

    def set_column_visible(self, column: str, visible: bool) -> None:
        """컬럼 가시성 설정"""
        if column in self._column_configs:
            self.beginResetModel()
            self._column_configs[column].visible = visible
            self.endResetModel()

    def set_column_order(self, order: List[str]) -> None:
        """컬럼 순서 설정"""
        self.beginResetModel()
        self._column_order = order
        self.endResetModel()

    def get_row_data(self, row: int) -> Dict[str, Any]:
        """특정 행의 데이터 반환"""
        if self._display_data is None or row >= len(self._display_data):
            return {}

        return {col: self._display_data[row, col] for col in self._display_data.columns}

    def get_marked_dataframe(self) -> Optional[pl.DataFrame]:
        """마킹된 데이터프레임 반환"""
        return self._display_data

    def export_as_text(self, delimiter: str = "\t") -> str:
        """텍스트로 내보내기 (클립보드용)"""
        if self._display_data is None:
            return ""

        visible_cols = self.get_visible_columns()
        lines = []

        # 헤더
        headers = []
        for col in visible_cols:
            config = self._column_configs.get(col)
            headers.append(config.display_name if config and config.display_name else col)
        lines.append(delimiter.join(headers))

        # 데이터
        for row in range(len(self._display_data)):
            row_data = []
            for col in visible_cols:
                value = self._display_data[row, col]
                config = self._column_configs.get(col)
                formatted = config.format_value(value) if config else str(value)
                row_data.append(formatted)
            lines.append(delimiter.join(row_data))

        return "\n".join(lines)

    def export_to_csv(self, file_path: str) -> None:
        """CSV로 내보내기"""
        if self._display_data is None:
            return

        visible_cols = self.get_visible_columns()
        export_df = self._display_data.select(visible_cols)
        export_df.write_csv(file_path)


class DetailsOnDemandPanel(QWidget):
    """
    Details-on-Demand 패널

    마킹된 데이터의 상세 정보를 표시하는 UI 패널입니다.
    """

    # 시그널
    row_clicked = Signal(int)  # 원본 데이터의 행 인덱스
    row_double_clicked = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)

        self._model = DetailsOnDemandModel()
        self._marked_indices_list: List[int] = []  # 순서 유지용

        self._setup_ui()

    def _setup_ui(self) -> None:
        """UI 설정"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 헤더
        header = self._create_header()
        layout.addWidget(header)

        # 테이블
        self._table = QTableView()
        self._table.setModel(self._model)
        self._table.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self._table.setAlternatingRowColors(True)
        self._table.setSortingEnabled(True)

        # 헤더 설정
        h_header = self._table.horizontalHeader()
        h_header.setStretchLastSection(True)
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        v_header = self._table.verticalHeader()
        v_header.setDefaultSectionSize(24)
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)

        # 컨텍스트 메뉴
        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._show_context_menu)

        # 클릭 이벤트
        self._table.clicked.connect(self._on_row_clicked)
        self._table.doubleClicked.connect(self._on_row_double_clicked)

        layout.addWidget(self._table)

        # 상태바
        self._status_label = QLabel("No items marked")
        self._status_label.setStyleSheet("color: gray; padding: 2px;")
        layout.addWidget(self._status_label)

    def _create_header(self) -> QFrame:
        """헤더 프레임 생성"""
        frame = QFrame()
        frame.setFrameStyle(QFrame.Shape.NoFrame)

        layout = QHBoxLayout(frame)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 제목
        title = QLabel("Details-on-Demand")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)

        layout.addStretch()

        # 컬럼 설정 버튼
        columns_btn = QToolButton()
        columns_btn.setText("Columns")
        columns_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        columns_btn.setMenu(self._create_columns_menu())
        layout.addWidget(columns_btn)
        self._columns_btn = columns_btn

        # 복사 버튼
        copy_btn = QPushButton("Copy")
        copy_btn.setMaximumWidth(60)
        copy_btn.clicked.connect(self._copy_to_clipboard)
        layout.addWidget(copy_btn)

        # 내보내기 버튼
        export_btn = QPushButton("Export")
        export_btn.setMaximumWidth(60)
        export_btn.clicked.connect(self._export_to_file)
        layout.addWidget(export_btn)

        return frame

    def _create_columns_menu(self) -> QMenu:
        """컬럼 선택 메뉴 생성"""
        menu = QMenu(self)

        # 메뉴는 데이터가 설정되면 동적으로 업데이트
        menu.aboutToShow.connect(self._update_columns_menu)

        return menu

    def _update_columns_menu(self) -> None:
        """컬럼 메뉴 업데이트"""
        menu = self._columns_btn.menu()
        menu.clear()

        for col in self._model._column_order:
            config = self._model._column_configs.get(col)
            if config:
                action = QAction(config.display_name or col, menu)
                action.setCheckable(True)
                action.setChecked(config.visible)
                action.triggered.connect(
                    lambda checked, c=col: self._model.set_column_visible(c, checked)
                )
                menu.addAction(action)

    def _show_context_menu(self, pos) -> None:
        """컨텍스트 메뉴 표시"""
        menu = QMenu(self)

        copy_action = QAction("Copy Selected", menu)
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction(copy_action)

        copy_all_action = QAction("Copy All", menu)
        copy_all_action.triggered.connect(self._copy_to_clipboard)
        menu.addAction(copy_all_action)

        menu.addSeparator()

        export_action = QAction("Export to CSV...", menu)
        export_action.triggered.connect(self._export_to_file)
        menu.addAction(export_action)

        menu.exec(self._table.mapToGlobal(pos))

    def _on_row_clicked(self, index: QModelIndex) -> None:
        """행 클릭 이벤트"""
        if index.isValid() and index.row() < len(self._marked_indices_list):
            original_idx = self._marked_indices_list[index.row()]
            self.row_clicked.emit(original_idx)

    def _on_row_double_clicked(self, index: QModelIndex) -> None:
        """행 더블클릭 이벤트"""
        if index.isValid() and index.row() < len(self._marked_indices_list):
            original_idx = self._marked_indices_list[index.row()]
            self.row_double_clicked.emit(original_idx)

    def _copy_to_clipboard(self) -> None:
        """전체 클립보드 복사"""
        text = self._model.export_as_text()
        clipboard = QApplication.clipboard()
        clipboard.setText(text)

    def _copy_selected(self) -> None:
        """선택된 행 복사"""
        selection = self._table.selectionModel()
        if not selection.hasSelection():
            return

        selected_rows = set(idx.row() for idx in selection.selectedIndexes())

        lines = []
        visible_cols = self._model.get_visible_columns()

        # 헤더
        headers = []
        for col in visible_cols:
            config = self._model._column_configs.get(col)
            headers.append(config.display_name if config and config.display_name else col)
        lines.append("\t".join(headers))

        # 데이터
        df = self._model.get_marked_dataframe()
        if df is not None:
            for row in sorted(selected_rows):
                if row < len(df):
                    row_data = []
                    for col in visible_cols:
                        value = df[row, col]
                        config = self._model._column_configs.get(col)
                        formatted = config.format_value(value) if config else str(value)
                        row_data.append(formatted)
                    lines.append("\t".join(row_data))

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(lines))

    def _export_to_file(self) -> None:
        """파일로 내보내기"""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Details",
            "details.csv",
            "CSV Files (*.csv);;All Files (*)"
        )

        if file_path:
            self._model.export_to_csv(file_path)

    def set_data(self, data: pl.DataFrame) -> None:
        """데이터 설정"""
        self._model.set_data(data)
        self._update_status()

    def set_marked_indices(self, indices: Set[int]) -> None:
        """마킹된 인덱스 설정"""
        self._marked_indices_list = sorted(indices)
        self._model.set_marked_indices(indices)
        self._update_status()

    def _update_status(self) -> None:
        """상태 레이블 업데이트"""
        count = self._model.rowCount()
        if count == 0:
            self._status_label.setText("No items marked")
        else:
            self._status_label.setText(f"{count} item(s) marked")

    def set_column_config(self, column: str, **kwargs) -> None:
        """컬럼 설정"""
        if column in self._model._column_configs:
            config = self._model._column_configs[column]
            for key, value in kwargs.items():
                if hasattr(config, key):
                    setattr(config, key, value)

    def clear(self) -> None:
        """클리어"""
        self._marked_indices_list = []
        self._model.set_marked_indices(set())
        self._update_status()
