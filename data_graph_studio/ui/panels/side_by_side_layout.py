"""
Side-by-Side Layout - 병렬 비교 레이아웃

여러 데이터셋을 독립된 패널에 병렬로 표시
"""

from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSplitter, QScrollArea, QGroupBox, QCheckBox,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal

from ...core.data_engine import DataEngine
from ...core.state import AppState, ComparisonMode


class MiniGraphWidget(QWidget):
    """미니 그래프 위젯 (병렬 비교용)"""

    activated = Signal(str)  # dataset_id

    def __init__(self, dataset_id: str, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.dataset_id = dataset_id
        self.engine = engine
        self.state = state

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 헤더
        metadata = self.state.get_dataset_metadata(self.dataset_id)
        name = metadata.name if metadata else self.dataset_id
        color = metadata.color if metadata else '#1f77b4'

        header = QFrame()
        header.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        header.setFixedHeight(30)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        name_label = QLabel(name)
        name_label.setStyleSheet("color: white; font-weight: bold;")
        header_layout.addWidget(name_label)

        # 행 수
        dataset = self.engine.get_dataset(self.dataset_id)
        row_count = dataset.row_count if dataset else 0
        rows_label = QLabel(f"{row_count:,} rows")
        rows_label.setStyleSheet("color: rgba(255,255,255,0.8);")
        header_layout.addWidget(rows_label)

        layout.addWidget(header)

        # 그래프 플레이스홀더
        try:
            import pyqtgraph as pg

            self.plot_widget = pg.PlotWidget()
            self.plot_widget.setBackground('w')
            self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
            self.plot_widget.setMinimumHeight(150)
            layout.addWidget(self.plot_widget, 1)

            # 간단한 데이터 플롯
            self._plot_data(color)
        except ImportError:
            # PyQtGraph 없으면 플레이스홀더
            placeholder = QLabel("Graph")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setStyleSheet("background: #f0f0f0; border: 1px solid #ddd;")
            placeholder.setMinimumHeight(150)
            layout.addWidget(placeholder, 1)

        # 통계 요약
        stats_frame = QFrame()
        stats_frame.setStyleSheet("background: #f8f9fa; border-radius: 4px; padding: 4px;")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)

        if dataset and dataset.df is not None:
            # 숫자 컬럼 통계
            numeric_cols = self.engine.get_numeric_columns(self.dataset_id)
            if numeric_cols:
                col = numeric_cols[0]
                series = dataset.df[col]
                stats_layout.addWidget(QLabel(f"Mean: {series.mean():.2f}"))
                stats_layout.addWidget(QLabel(f"Min: {series.min():.2f}"))
                stats_layout.addWidget(QLabel(f"Max: {series.max():.2f}"))

        stats_layout.addStretch()
        layout.addWidget(stats_frame)

    def _plot_data(self, color: str):
        """간단한 데이터 플롯"""
        import numpy as np

        dataset = self.engine.get_dataset(self.dataset_id)
        if not dataset or dataset.df is None:
            return

        # X축 데이터
        x_col = self.state.x_column
        df = dataset.df

        if x_col and x_col in df.columns:
            try:
                x_data = df[x_col].to_numpy()
            except:
                x_data = np.arange(len(df))
        else:
            x_data = np.arange(len(df))

        # Y축 데이터 - 첫 번째 숫자 컬럼
        y_data = None
        if self.state.value_columns:
            y_col = self.state.value_columns[0].name
            if y_col in df.columns:
                try:
                    y_data = df[y_col].to_numpy()
                except:
                    pass

        if y_data is None:
            numeric_cols = self.engine.get_numeric_columns(self.dataset_id)
            if numeric_cols:
                y_data = df[numeric_cols[0]].to_numpy()

        if y_data is None:
            return

        # 샘플링
        max_points = 1000
        if len(x_data) > max_points:
            step = len(x_data) // max_points
            x_data = x_data[::step]
            y_data = y_data[::step]

        # 플롯
        try:
            import pyqtgraph as pg
            self.plot_widget.plot(x_data, y_data, pen=pg.mkPen(color, width=2))
        except:
            pass

    def refresh(self):
        """새로고침"""
        self._setup_ui()

    def mousePressEvent(self, event):
        """클릭 시 활성화"""
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.dataset_id)
        super().mousePressEvent(event)


class SideBySideLayout(QWidget):
    """
    병렬 비교 레이아웃

    여러 데이터셋을 독립된 패널에 나란히 표시
    """

    dataset_activated = Signal(str)  # dataset_id

    MAX_PANELS = 4  # 최대 동시 표시 패널 수

    def __init__(self, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.state = state

        self._panels: Dict[str, MiniGraphWidget] = {}
        self._sync_scroll = True
        self._sync_zoom = True

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 동기화 옵션
        options_frame = QFrame()
        options_frame.setStyleSheet("background: #f8f9fa; border-bottom: 1px solid #ddd;")
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(8, 4, 8, 4)

        options_layout.addWidget(QLabel("Sync:"))

        self.sync_scroll_cb = QCheckBox("Scroll")
        self.sync_scroll_cb.setChecked(self._sync_scroll)
        self.sync_scroll_cb.stateChanged.connect(self._on_sync_scroll_changed)
        options_layout.addWidget(self.sync_scroll_cb)

        self.sync_zoom_cb = QCheckBox("Zoom")
        self.sync_zoom_cb.setChecked(self._sync_zoom)
        self.sync_zoom_cb.stateChanged.connect(self._on_sync_zoom_changed)
        options_layout.addWidget(self.sync_zoom_cb)

        options_layout.addStretch()
        layout.addWidget(options_frame)

        # 패널 스플리터
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

    def _connect_signals(self):
        """시그널 연결"""
        self.state.comparison_settings_changed.connect(self.refresh)
        self.state.dataset_added.connect(self._on_dataset_added)
        self.state.dataset_removed.connect(self._on_dataset_removed)

    def _on_sync_scroll_changed(self, state):
        self._sync_scroll = state == Qt.Checked
        self.state.update_comparison_settings(sync_scroll=self._sync_scroll)

    def _on_sync_zoom_changed(self, state):
        self._sync_zoom = state == Qt.Checked
        self.state.update_comparison_settings(sync_zoom=self._sync_zoom)

    def _on_dataset_added(self, dataset_id: str):
        """데이터셋 추가됨"""
        self.refresh()

    def _on_dataset_removed(self, dataset_id: str):
        """데이터셋 제거됨"""
        if dataset_id in self._panels:
            panel = self._panels[dataset_id]
            self.splitter.widget(self.splitter.indexOf(panel)).setParent(None)
            del self._panels[dataset_id]

    def refresh(self):
        """비교 대상 데이터셋으로 패널 새로고침"""
        # 기존 패널 제거
        while self.splitter.count() > 0:
            widget = self.splitter.widget(0)
            widget.setParent(None)
        self._panels.clear()

        # 비교 대상 데이터셋
        dataset_ids = self.state.comparison_dataset_ids[:self.MAX_PANELS]

        if not dataset_ids:
            # 활성 데이터셋만 표시
            active_id = self.state.active_dataset_id
            if active_id:
                dataset_ids = [active_id]

        for dataset_id in dataset_ids:
            panel = MiniGraphWidget(dataset_id, self.engine, self.state)
            panel.activated.connect(self._on_panel_activated)
            self._panels[dataset_id] = panel
            self.splitter.addWidget(panel)

        # 동일 크기로 분할
        if self.splitter.count() > 0:
            sizes = [self.splitter.width() // self.splitter.count()] * self.splitter.count()
            self.splitter.setSizes(sizes)

    def _on_panel_activated(self, dataset_id: str):
        """패널 활성화"""
        self.dataset_activated.emit(dataset_id)

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """비교 대상 데이터셋 설정"""
        self.state.set_comparison_datasets(dataset_ids[:self.MAX_PANELS])
        self.refresh()
