"""
Dataset Manager Panel - 멀티 데이터셋 관리 패널

데이터셋 추가, 제거, 전환, 비교 설정 UI
"""

from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QFrame, QComboBox,
    QCheckBox, QMenu, QColorDialog, QInputDialog,
    QMessageBox, QSizePolicy, QScrollArea, QGroupBox,
    QSplitter, QToolButton, QFileDialog, QTreeWidget, QTreeWidgetItem
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QColor, QIcon, QPixmap, QPainter, QBrush, QAction

from ...core.data_engine import DataEngine, DatasetInfo
from ...core.state import (
    AppState, ComparisonMode, DatasetMetadata,
    DEFAULT_DATASET_COLORS
)
from ...core.profile import Profile, GraphSetting


class DatasetItemWidget(QFrame):
    """개별 데이터셋 아이템 위젯"""

    activated = Signal(str)  # dataset_id
    removed = Signal(str)  # dataset_id
    color_changed = Signal(str, str)  # dataset_id, color
    compare_toggled = Signal(str, bool)  # dataset_id, enabled

    def __init__(
        self,
        dataset_id: str,
        metadata: DatasetMetadata,
        dataset_info: DatasetInfo,
        parent=None
    ):
        super().__init__(parent)
        self.dataset_id = dataset_id
        self.metadata = metadata
        self.dataset_info = dataset_info

        self.setFrameStyle(QFrame.StyledPanel | QFrame.Raised)
        self.setLineWidth(1)
        self._setup_ui()
        self._update_style()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # 상단: 색상 + 이름 + 버튼들
        top_layout = QHBoxLayout()
        top_layout.setSpacing(6)

        # 색상 버튼
        self.color_btn = QToolButton()
        self.color_btn.setToolTip("Change dataset color")
        self.color_btn.setFixedSize(20, 20)
        self._update_color_button()
        self.color_btn.clicked.connect(self._on_color_click)
        top_layout.addWidget(self.color_btn)

        # 이름
        self.name_label = QLabel(self.metadata.name)
        self.name_label.setObjectName("datasetName")
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        top_layout.addWidget(self.name_label)

        # 활성 표시
        self.active_label = QLabel("●")
        self.active_label.setObjectName("datasetActiveLabel")
        self.active_label.setVisible(self.metadata.is_active)
        top_layout.addWidget(self.active_label)

        # 비교 체크박스
        self.compare_cb = QCheckBox()
        self.compare_cb.setChecked(self.metadata.compare_enabled)
        self.compare_cb.setToolTip("비교에 포함")
        self.compare_cb.stateChanged.connect(self._on_compare_changed)
        top_layout.addWidget(self.compare_cb)

        # 삭제 버튼
        self.remove_btn = QToolButton()
        self.remove_btn.setText("×")
        self.remove_btn.setToolTip("Remove this dataset")
        self.remove_btn.setFixedSize(20, 20)
        self.remove_btn.setObjectName("datasetRemoveBtn")
        self.remove_btn.clicked.connect(self._on_remove_click)
        top_layout.addWidget(self.remove_btn)

        layout.addLayout(top_layout)

        # 하단: 정보
        info_layout = QHBoxLayout()
        info_layout.setSpacing(10)

        # 행 수
        rows_text = f"{self.dataset_info.row_count:,}" if self.dataset_info else "0"
        self.rows_label = QLabel(f"📊 {rows_text} rows")
        self.rows_label.setObjectName("datasetStat")
        info_layout.addWidget(self.rows_label)

        # 컬럼 수
        cols_text = f"{self.dataset_info.column_count}" if self.dataset_info else "0"
        self.cols_label = QLabel(f"× {cols_text} cols")
        self.cols_label.setObjectName("datasetStat")
        info_layout.addWidget(self.cols_label)

        # 메모리
        memory_mb = self.metadata.memory_bytes / (1024 * 1024)
        self.memory_label = QLabel(f"💾 {memory_mb:.1f} MB")
        self.memory_label.setObjectName("datasetStat")
        info_layout.addWidget(self.memory_label)

        info_layout.addStretch()
        layout.addLayout(info_layout)

    def _update_color_button(self):
        """색상 버튼 업데이트"""
        pixmap = QPixmap(16, 16)
        pixmap.fill(QColor(self.metadata.color))
        self.color_btn.setIcon(QIcon(pixmap))

    def _update_style(self):
        """선택 상태에 따른 스타일 업데이트"""
        self.setObjectName("datasetItem")
        if self.metadata.is_active:
            self.setProperty("active", "true")
        else:
            self.setProperty("active", "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def set_active(self, active: bool):
        """활성 상태 설정"""
        self.metadata.is_active = active
        self.active_label.setVisible(active)
        self._update_style()

    def update_info(self, metadata: DatasetMetadata, dataset_info: DatasetInfo):
        """정보 업데이트"""
        self.metadata = metadata
        self.dataset_info = dataset_info

        self.name_label.setText(metadata.name)
        self._update_color_button()
        self.compare_cb.setChecked(metadata.compare_enabled)

        rows_text = f"{dataset_info.row_count:,}" if dataset_info else "0"
        self.rows_label.setText(f"📊 {rows_text} rows")

        cols_text = f"{dataset_info.column_count}" if dataset_info else "0"
        self.cols_label.setText(f"× {cols_text} cols")

        memory_mb = metadata.memory_bytes / (1024 * 1024)
        self.memory_label.setText(f"💾 {memory_mb:.1f} MB")

        self._update_style()

    def _on_color_click(self):
        """색상 선택"""
        color = QColorDialog.getColor(
            QColor(self.metadata.color),
            self,
            "데이터셋 색상 선택"
        )
        if color.isValid():
            self.color_changed.emit(self.dataset_id, color.name())

    def _on_remove_click(self):
        """삭제 버튼 클릭"""
        self.removed.emit(self.dataset_id)

    def _on_compare_changed(self, state):
        """비교 체크박스 변경"""
        self.compare_toggled.emit(self.dataset_id, state == Qt.Checked)

    def mousePressEvent(self, event):
        """클릭 시 활성화"""
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.dataset_id)
        super().mousePressEvent(event)

    # Issue #13 — signal for state-level rename (not just UI label)
    renamed = Signal(str, str)  # dataset_id, new_name

    def mouseDoubleClickEvent(self, event):
        """더블클릭 시 이름 변경"""
        if event.button() == Qt.LeftButton:
            new_name, ok = QInputDialog.getText(
                self, "데이터셋 이름 변경",
                "새 이름:", text=self.metadata.name
            )
            if ok and new_name:
                self.name_label.setText(new_name)
                self.renamed.emit(self.dataset_id, new_name)


class DatasetManagerPanel(QWidget):
    """
    데이터셋 관리 패널

    Features:
    - 로드된 데이터셋 목록 표시
    - 데이터셋 추가/제거
    - 활성 데이터셋 전환
    - 비교 모드 선택
    - 비교 대상 데이터셋 선택
    """

    # Signals
    dataset_activated = Signal(str)  # dataset_id
    dataset_removed = Signal(str)  # dataset_id
    add_dataset_requested = Signal()
    comparison_mode_changed = Signal(str)  # mode
    comparison_started = Signal(list)  # [dataset_ids]

    def __init__(self, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.state = state

        self._dataset_widgets: Dict[str, DatasetItemWidget] = {}
        self._dataset_items: Dict[str, QTreeWidgetItem] = {}

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 헤더
        header_layout = QHBoxLayout()

        title = QLabel("📂 Datasets")
        title.setObjectName("datasetPanelTitle")
        header_layout.addWidget(title)

        header_layout.addStretch()

        # 데이터셋 수 표시
        self.count_label = QLabel("0 / 10")
        self.count_label.setObjectName("datasetCount")
        header_layout.addWidget(self.count_label)

        layout.addLayout(header_layout)

        # 데이터셋/프로파일 트리
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(18)
        self.tree.setObjectName("datasetTree")
        self.tree.itemClicked.connect(self._on_tree_clicked)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_tree_context_menu)
        layout.addWidget(self.tree, 1)

        # Buttons row
        btn_row = QHBoxLayout()
        self.add_btn = QPushButton("+ 데이터셋 추가")
        self.add_btn.setToolTip("Add a new dataset from file")
        self.add_btn.setObjectName("datasetAddBtn")
        self.add_btn.clicked.connect(self._on_add_click)
        btn_row.addWidget(self.add_btn)

        self.save_profile_btn = QPushButton("💾 프로파일 저장")
        self.save_profile_btn.setToolTip("Save current graph settings as a profile")
        self.save_profile_btn.setObjectName("datasetProfileBtn")
        self.save_profile_btn.clicked.connect(self._on_save_profile)
        btn_row.addWidget(self.save_profile_btn)

        self.load_profile_btn = QPushButton("📂 프로파일 불러오기")
        self.load_profile_btn.setToolTip("Load a saved profile from file")
        self.load_profile_btn.setObjectName("datasetProfileBtn")
        self.load_profile_btn.clicked.connect(self._on_load_profile)
        btn_row.addWidget(self.load_profile_btn)

        layout.addLayout(btn_row)

        # 구분선
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        layout.addWidget(line)

        # 비교 모드 설정
        compare_group = QGroupBox("비교 모드")
        compare_layout = QVBoxLayout(compare_group)
        compare_layout.setSpacing(6)

        # 모드 선택 콤보박스
        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("모드:"))

        self.mode_combo = QComboBox()
        self.mode_combo.setToolTip("Select comparison visualization mode")
        self.mode_combo.addItem("단일", ComparisonMode.SINGLE.value)
        self.mode_combo.addItem("오버레이", ComparisonMode.OVERLAY.value)
        self.mode_combo.addItem("병렬", ComparisonMode.SIDE_BY_SIDE.value)
        self.mode_combo.addItem("차이 분석", ComparisonMode.DIFFERENCE.value)
        self.mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        mode_layout.addWidget(self.mode_combo, 1)

        compare_layout.addLayout(mode_layout)

        # 키 컬럼 설정
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("키 컬럼:"))

        self.key_combo = QComboBox()
        self.key_combo.setToolTip("Column used to align rows across datasets")
        self.key_combo.setEnabled(False)
        self.key_combo.currentTextChanged.connect(self._on_key_column_changed)
        key_layout.addWidget(self.key_combo, 1)

        compare_layout.addLayout(key_layout)

        # 동기화 옵션
        sync_layout = QHBoxLayout()
        self.sync_scroll_cb = QCheckBox("스크롤")
        self.sync_scroll_cb.setToolTip("Synchronize table scroll across datasets")
        self.sync_scroll_cb.setChecked(True)
        self.sync_scroll_cb.stateChanged.connect(self._on_sync_changed)
        sync_layout.addWidget(self.sync_scroll_cb)

        self.sync_zoom_cb = QCheckBox("줌")
        self.sync_zoom_cb.setToolTip("Synchronize chart zoom across datasets")
        self.sync_zoom_cb.setChecked(True)
        self.sync_zoom_cb.stateChanged.connect(self._on_sync_changed)
        sync_layout.addWidget(self.sync_zoom_cb)

        self.sync_select_cb = QCheckBox("선택")
        self.sync_select_cb.setToolTip("Synchronize data selection across datasets")
        self.sync_select_cb.stateChanged.connect(self._on_sync_changed)
        sync_layout.addWidget(self.sync_select_cb)

        # Pan sync (graph)
        self.sync_pan_x_cb = QCheckBox("X 패닝")
        self.sync_pan_x_cb.setToolTip("Synchronize X-axis panning")
        self.sync_pan_x_cb.setChecked(True)
        self.sync_pan_x_cb.stateChanged.connect(self._on_sync_changed)
        sync_layout.addWidget(self.sync_pan_x_cb)

        self.sync_pan_y_cb = QCheckBox("Y 패닝")
        self.sync_pan_y_cb.setToolTip("Synchronize Y-axis panning")
        self.sync_pan_y_cb.setChecked(True)
        self.sync_pan_y_cb.stateChanged.connect(self._on_sync_changed)
        sync_layout.addWidget(self.sync_pan_y_cb)

        compare_layout.addLayout(sync_layout)

        # 비교 시작 버튼
        self.compare_btn = QPushButton("비교 시작")
        self.compare_btn.setToolTip("Start comparison with selected datasets")
        self.compare_btn.setEnabled(False)
        self.compare_btn.clicked.connect(self._on_compare_click)
        compare_layout.addWidget(self.compare_btn)

        layout.addWidget(compare_group)

        # 메모리 사용량
        self.memory_label = QLabel("💾 메모리: 0 MB / 4 GB")
        self.memory_label.setObjectName("datasetMemory")
        layout.addWidget(self.memory_label)

    def _connect_signals(self):
        """시그널 연결"""
        # State 시그널
        self.state.dataset_added.connect(self._on_dataset_added)
        self.state.dataset_removed.connect(self._on_dataset_removed)
        self.state.dataset_activated.connect(self._on_dataset_activated)
        self.state.dataset_updated.connect(self._on_dataset_updated)
        self.state.comparison_settings_changed.connect(self._on_comparison_settings_changed)

    def _on_add_click(self):
        """데이터셋 추가 버튼 클릭"""
        self.add_dataset_requested.emit()

    def _on_mode_changed(self, index):
        """비교 모드 변경"""
        mode_value = self.mode_combo.itemData(index)
        self.comparison_mode_changed.emit(mode_value)

        # 모드에 따라 UI 업데이트
        is_comparison = mode_value != ComparisonMode.SINGLE.value
        self.key_combo.setEnabled(is_comparison)
        self._update_compare_button()
        self._update_key_column_combo()

    def _on_key_column_changed(self, column: str):
        """키 컬럼 변경"""
        if column:
            self.state.update_comparison_settings(key_column=column)

    def _on_sync_changed(self):
        """동기화 옵션 변경"""
        self.state.update_comparison_settings(
            sync_scroll=self.sync_scroll_cb.isChecked(),
            sync_zoom=self.sync_zoom_cb.isChecked(),
            sync_pan_x=self.sync_pan_x_cb.isChecked(),
            sync_pan_y=self.sync_pan_y_cb.isChecked(),
            sync_selection=self.sync_select_cb.isChecked()
        )

    def _on_compare_click(self):
        """비교 시작 버튼 클릭"""
        compare_ids = self._get_comparison_dataset_ids()
        if len(compare_ids) >= 2:
            self.comparison_started.emit(compare_ids)

    def _on_dataset_added(self, dataset_id: str):
        """데이터셋 추가됨"""
        self._add_dataset_widget(dataset_id)
        self._update_tree()
        self._update_count_label()
        self._update_memory_label()
        self._update_compare_button()
        self._update_key_column_combo()

    def _on_dataset_removed(self, dataset_id: str):
        """데이터셋 제거됨"""
        self._remove_dataset_widget(dataset_id)
        self._update_tree()
        self._update_count_label()
        self._update_memory_label()
        self._update_compare_button()
        self._update_key_column_combo()

    def _on_dataset_activated(self, dataset_id: str):
        """데이터셋 활성화됨"""
        for did, widget in self._dataset_widgets.items():
            widget.set_active(did == dataset_id)

    def _on_dataset_updated(self, dataset_id: str):
        """데이터셋 업데이트됨"""
        if dataset_id in self._dataset_widgets:
            metadata = self.state.get_dataset_metadata(dataset_id)
            dataset_info = self.engine.get_dataset(dataset_id)
            if metadata and dataset_info:
                self._dataset_widgets[dataset_id].update_info(metadata, dataset_info)
        self._update_tree()

    def _on_comparison_settings_changed(self):
        """비교 설정 변경됨"""
        settings = self.state.comparison_settings
        self.mode_combo.setCurrentIndex(
            self.mode_combo.findData(settings.mode.value)
        )
        self.sync_scroll_cb.setChecked(settings.sync_scroll)
        self.sync_zoom_cb.setChecked(settings.sync_zoom)
        self.sync_pan_x_cb.setChecked(settings.sync_pan_x)
        self.sync_pan_y_cb.setChecked(settings.sync_pan_y)
        self.sync_select_cb.setChecked(settings.sync_selection)
        self._update_compare_button()

    def _add_dataset_widget(self, dataset_id: str):
        """데이터셋 위젯 추가"""
        metadata = self.state.get_dataset_metadata(dataset_id)
        dataset_info = self.engine.get_dataset(dataset_id)

        if not metadata or not dataset_info:
            return

        widget = DatasetItemWidget(dataset_id, metadata, dataset_info)
        widget.activated.connect(self._on_widget_activated)
        widget.removed.connect(self._on_widget_removed)
        widget.color_changed.connect(self._on_widget_color_changed)
        widget.compare_toggled.connect(self._on_widget_compare_toggled)

        # 스트레치 앞에 삽입 (legacy UI kept hidden)
        self._dataset_widgets[dataset_id] = widget

    def _remove_dataset_widget(self, dataset_id: str):
        """데이터셋 위젯 제거"""
        if dataset_id in self._dataset_widgets:
            widget = self._dataset_widgets[dataset_id]
            widget.deleteLater()
            del self._dataset_widgets[dataset_id]
        if dataset_id in self._dataset_items:
            item = self._dataset_items.pop(dataset_id)
            idx = self.tree.indexOfTopLevelItem(item)
            if idx >= 0:
                self.tree.takeTopLevelItem(idx)

    def _on_widget_activated(self, dataset_id: str):
        """위젯 활성화 요청"""
        self.dataset_activated.emit(dataset_id)

    # ---------------- Project Explorer Tree ----------------
    def _update_tree(self):
        self.tree.clear()
        self._dataset_items.clear()
        for dataset_id, meta in self.state.dataset_metadata.items():
            proj_text = meta.name
            proj_item = QTreeWidgetItem([proj_text])
            proj_item.setData(0, Qt.UserRole, ("dataset", dataset_id))
            if meta.is_active:
                proj_item.setExpanded(True)
                proj_item.setSelected(True)
            # Add profiles (chart type + name)
            for setting in self.state.get_dataset_profiles(dataset_id):
                label = f"{setting.chart_type.upper()} | {setting.name}"
                child = QTreeWidgetItem([label])
                child.setData(0, Qt.UserRole, ("profile", dataset_id, setting.id))
                proj_item.addChild(child)
            self.tree.addTopLevelItem(proj_item)
            self._dataset_items[dataset_id] = proj_item
        self.tree.expandToDepth(0)

    def _on_tree_clicked(self, item: QTreeWidgetItem, column: int):
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind = data[0]
        if kind == "dataset":
            dataset_id = data[1]
            self.dataset_activated.emit(dataset_id)
        elif kind == "profile":
            dataset_id, setting_id = data[1], data[2]
            # Apply profile
            setting = next((s for s in self.state.get_dataset_profiles(dataset_id) if s.id == setting_id), None)
            if setting:
                self.state.apply_graph_setting(setting)

    def _on_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        if not item:
            return
        data = item.data(0, Qt.UserRole)
        if not data:
            return
        kind = data[0]
        menu = QMenu(self)
        if kind == "dataset":
            dataset_id = data[1]
            save_act = QAction("💾 Save Profile", self)
            save_act.triggered.connect(lambda: self._save_profile_for_dataset(dataset_id))
            menu.addAction(save_act)
        elif kind == "profile":
            dataset_id, setting_id = data[1], data[2]
            rename_act = QAction("✏️ Rename", self)
            rename_act.triggered.connect(lambda: self._rename_profile(dataset_id, setting_id))
            menu.addAction(rename_act)
            del_act = QAction("🗑️ Delete", self)
            del_act.triggered.connect(lambda: self._delete_profile(dataset_id, setting_id))
            menu.addAction(del_act)
        menu.exec(self.tree.mapToGlobal(pos))

    def _save_profile_for_dataset(self, dataset_id: str):
        name, ok = QInputDialog.getText(self, "Save Profile", "Profile name:")
        if not ok or not name.strip():
            return
        setting = self.state.build_graph_setting_from_state(name.strip(), dataset_id=dataset_id)
        self.state.add_graph_setting_to_dataset(dataset_id, setting)
        self._update_tree()

    def _rename_profile(self, dataset_id: str, setting_id: str):
        setting = next((s for s in self.state.get_dataset_profiles(dataset_id) if s.id == setting_id), None)
        if not setting:
            return
        name, ok = QInputDialog.getText(self, "Rename Profile", "New name:", text=setting.name)
        if ok and name.strip():
            self.state.rename_graph_setting(dataset_id, setting_id, name.strip())
            self._update_tree()

    def _delete_profile(self, dataset_id: str, setting_id: str):
        reply = QMessageBox.question(self, "Delete Profile", "Delete this profile?", QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.state.remove_graph_setting(dataset_id, setting_id)
            self._update_tree()

    def _on_save_profile(self):
        if not self.state.active_dataset_id:
            return
        self._save_profile_for_dataset(self.state.active_dataset_id)

    def _on_load_profile(self):
        path, _ = QFileDialog.getOpenFileName(self, "Load Profile", "", "Data Graph Profile (*.dgp)")
        if not path or not self.state.active_dataset_id:
            return
        try:
            profile = Profile.load(path)
            for setting in profile.settings:
                self.state.add_graph_setting_to_dataset(self.state.active_dataset_id, setting)
            self._update_tree()
        except Exception as e:
            QMessageBox.warning(self, "Load Profile", f"Failed to load profile: {e}")

    def _on_widget_removed(self, dataset_id: str):
        """위젯 제거 요청"""
        reply = QMessageBox.question(
            self, "데이터셋 제거",
            f"데이터셋을 제거하시겠습니까?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.dataset_removed.emit(dataset_id)

    def _on_widget_color_changed(self, dataset_id: str, color: str):
        """위젯 색상 변경"""
        self.state.set_dataset_color(dataset_id, color)
        self.engine.set_dataset_color(dataset_id, color)

    def _on_widget_compare_toggled(self, dataset_id: str, enabled: bool):
        """위젯 비교 토글"""
        self.state.toggle_dataset_comparison(dataset_id)
        self._update_compare_button()

    def _update_count_label(self):
        """데이터셋 수 레이블 업데이트"""
        count = len(self._dataset_widgets)
        max_count = self.engine.MAX_DATASETS
        self.count_label.setText(f"{count} / {max_count}")

    def _update_memory_label(self):
        """메모리 사용량 레이블 업데이트"""
        used = self.engine.get_total_memory_usage()
        max_mem = self.engine.MAX_TOTAL_MEMORY
        used_mb = used / (1024 * 1024)
        max_gb = max_mem / (1024 * 1024 * 1024)
        self.memory_label.setText(f"💾 메모리: {used_mb:.0f} MB / {max_gb:.0f} GB")

    def _update_compare_button(self):
        """비교 버튼 상태 업데이트"""
        compare_ids = self._get_comparison_dataset_ids()
        mode = self.mode_combo.currentData()
        is_comparison = mode != ComparisonMode.SINGLE.value
        can_compare = is_comparison and len(compare_ids) >= 2
        self.compare_btn.setEnabled(can_compare)

    def _update_key_column_combo(self):
        """키 컬럼 콤보박스 업데이트"""
        compare_ids = self._get_comparison_dataset_ids()

        self.key_combo.clear()
        self.key_combo.addItem("(선택 안함)", "")

        if len(compare_ids) >= 2:
            # 공통 컬럼 찾기
            common_columns = self.engine.get_common_columns(compare_ids)
            for col in common_columns:
                self.key_combo.addItem(col, col)

    def _get_comparison_dataset_ids(self) -> List[str]:
        """비교 활성화된 데이터셋 ID 목록"""
        return [
            did for did, widget in self._dataset_widgets.items()
            if widget.compare_cb.isChecked()
        ]

    def apply_theme(self, is_light: bool = False):
        """Apply theme-aware styles.  Issue #5 — replaces hardcoded dark-only CSS."""
        if is_light:
            bg, fg, border, sel_bg = "#FFFFFF", "#1A202C", "#E2E8F0", "#EDF2F7"
            title_fg, stat_fg = "#1A202C", "#4A5568"
            btn_bg, btn_hover = "#38A169", "#2F855A"
        else:
            bg, fg, border, sel_bg = "#111827", "#E2E8F0", "#1F2937", "#1F2937"
            title_fg, stat_fg = "#F2F4F8", "#C9D1DB"
            btn_bg, btn_hover = "#4CAF50", "#45a049"

        self.setStyleSheet(f"""
            #datasetPanelTitle {{ font-size: 14px; font-weight: bold; color: {title_fg}; }}
            #datasetCount {{ color: {stat_fg}; }}
            #datasetMemory {{ color: {stat_fg}; font-size: 11px; }}
            #datasetTree {{
                background: {bg}; color: {fg};
                border: 1px solid {border}; border-radius: 6px;
            }}
            #datasetTree::item {{ padding: 6px; }}
            #datasetTree::item:selected {{ background: {sel_bg}; color: {fg}; }}
            #datasetAddBtn {{
                background-color: {btn_bg}; color: white; border: none;
                padding: 6px 8px; border-radius: 4px; font-size: 11px;
            }}
            #datasetAddBtn:hover {{ background-color: {btn_hover}; }}
            #datasetProfileBtn {{ font-size: 11px; padding: 6px 8px; }}
        """)

    def refresh(self):
        """전체 새로고침"""
        # 기존 위젯 모두 제거
        for widget in self._dataset_widgets.values():
            widget.deleteLater()
        self._dataset_widgets.clear()

        # 새로 추가
        for dataset_id in self.state.dataset_metadata.keys():
            self._add_dataset_widget(dataset_id)

        # 트리 뷰 갱신
        self._update_tree()
        self._update_count_label()
        self._update_memory_label()
        self._update_compare_button()
        self._update_key_column_combo()
