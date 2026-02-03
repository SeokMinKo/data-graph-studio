"""
Side-by-Side Layout - 병렬 비교 레이아웃

여러 데이터셋을 독립된 패널에 병렬로 표시
스크롤/줌 동기화 지원 (ViewSyncManager 사용)
"""

from typing import Optional, List, Dict, Any, TYPE_CHECKING
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QSplitter, QScrollArea, QGroupBox, QCheckBox,
    QSizePolicy, QPushButton
)
from PySide6.QtCore import Qt, Signal, QTimer

from ...core.data_engine import DataEngine
from ...core.state import AppState, ComparisonMode
from ...core.view_sync import ViewSyncManager

if TYPE_CHECKING:
    from ...core.profile import GraphSetting


class MiniGraphWidget(QWidget):
    """미니 그래프 위젯 (병렬 비교용)

    Supports two modes:
      1. Dataset mode (graph_setting=None) — uses AppState for columns/chart type.
      2. Profile mode (graph_setting provided) — uses GraphSetting for columns/chart type.

    Duck-typing interface for ViewSyncManager:
      - set_view_range(x_range, y_range, sync_x, sync_y)
      - set_selection(indices)
    """

    activated = Signal(str)  # dataset_id
    view_range_changed = Signal(str, list, list)  # dataset_id, x_range, y_range

    def __init__(
        self,
        dataset_id: str,
        engine: DataEngine,
        state: AppState,
        graph_setting: 'Optional[GraphSetting]' = None,
        parent=None,
    ):
        super().__init__(parent)
        self.dataset_id = dataset_id
        self.engine = engine
        self.state = state
        self.graph_setting = graph_setting
        self.plot_widget = None
        self._is_syncing = False  # 동기화 중인지 추적 (무한 루프 방지)
        self._selected_indices: list = []

        self._setup_ui()

    # ------------------------------------------------------------------
    # Effective columns (profile vs state)
    # ------------------------------------------------------------------

    @property
    def effective_x_column(self) -> Optional[str]:
        """X column: from graph_setting if present, else from state."""
        if self.graph_setting is not None:
            return self.graph_setting.x_column
        return self.state.x_column

    @property
    def effective_value_columns(self) -> list:
        """Value columns: from graph_setting (tuple of dicts) or state (list of ValueColumn).

        When graph_setting is provided, returns list(graph_setting.value_columns).
        When not, returns state.value_columns (list of ValueColumn dataclass instances).
        """
        if self.graph_setting is not None:
            return list(self.graph_setting.value_columns)
        return list(self.state.value_columns)

    @property
    def effective_chart_type(self) -> str:
        """Chart type string."""
        if self.graph_setting is not None:
            return self.graph_setting.chart_type or "line"
        try:
            return self.state.chart_settings.chart_type.value
        except Exception:
            return "line"

    @property
    def _header_name(self) -> str:
        """Display name for the header."""
        if self.graph_setting is not None:
            return self.graph_setting.name
        metadata = self.state.get_dataset_metadata(self.dataset_id)
        return metadata.name if metadata else self.dataset_id

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 헤더 — always use dataset color for background
        metadata = self.state.get_dataset_metadata(self.dataset_id)
        color = metadata.color if metadata else '#1f77b4'

        header = QFrame()
        header.setStyleSheet(f"background-color: {color}; border-radius: 4px;")
        header.setFixedHeight(30)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 4, 8, 4)

        name_label = QLabel(self._header_name)
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

            # ViewBox 범위 변경 시그널 연결
            self.plot_widget.getViewBox().sigRangeChanged.connect(self._on_view_range_changed)

            # 간단한 데이터 플롯
            self._plot_data(color)
        except ImportError:
            # PyQtGraph 없으면 플레이스홀더
            placeholder = QLabel("Graph")
            placeholder.setAlignment(Qt.AlignCenter)
            placeholder.setObjectName("graphPlaceholder")
            placeholder.setMinimumHeight(150)
            layout.addWidget(placeholder, 1)

        # 통계 요약
        stats_frame = QFrame()
        stats_frame.setObjectName("statsFrame")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(8, 4, 8, 4)

        if dataset and dataset.df is not None:
            # 숫자 컬럼 통계
            numeric_cols = self.engine.get_numeric_columns(self.dataset_id)
            if numeric_cols:
                col = numeric_cols[0]
                try:
                    series = dataset.df[col]
                    stats_layout.addWidget(QLabel(f"Mean: {series.mean():.2f}"))
                    stats_layout.addWidget(QLabel(f"Min: {series.min():.2f}"))
                    stats_layout.addWidget(QLabel(f"Max: {series.max():.2f}"))
                except Exception:
                    pass

        stats_layout.addStretch()
        layout.addWidget(stats_frame)

    def _plot_data(self, color: str):
        """간단한 데이터 플롯 — uses effective columns."""
        import numpy as np

        dataset = self.engine.get_dataset(self.dataset_id)
        if not dataset or dataset.df is None:
            return

        # X축 데이터
        x_col = self.effective_x_column
        df = dataset.df

        if x_col and x_col in df.columns:
            try:
                x_data = df[x_col].to_numpy()
            except Exception:
                x_data = np.arange(len(df))
        else:
            x_data = np.arange(len(df))

        # Y축 데이터 — use effective value columns
        y_data = None
        value_cols = self.effective_value_columns
        if value_cols:
            # value_cols may be ValueColumn objects or dicts
            first = value_cols[0]
            y_col = first.name if hasattr(first, 'name') else first.get('name', '')
            if y_col and y_col in df.columns:
                try:
                    y_data = df[y_col].to_numpy()
                except Exception:
                    pass

        if y_data is None:
            numeric_cols = self.engine.get_numeric_columns(self.dataset_id)
            if numeric_cols:
                try:
                    y_data = df[numeric_cols[0]].to_numpy()
                except Exception:
                    pass

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
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def refresh(self):
        """새로고침"""
        self._setup_ui()

    # ------------------------------------------------------------------
    # ViewSyncManager duck-typing interface
    # ------------------------------------------------------------------

    def set_view_range(self, x_range, y_range, sync_x: bool = True, sync_y: bool = True):
        """외부에서 뷰 범위 설정 (동기화용).

        When x_range/y_range are None → auto-range.
        """
        if self.plot_widget is None:
            return

        # Handle auto-range request from ViewSyncManager.reset_all_views()
        if x_range is None and y_range is None:
            self.plot_widget.getViewBox().autoRange()
            return

        self._is_syncing = True
        try:
            viewbox = self.plot_widget.getViewBox()
            if sync_x and sync_y:
                viewbox.setRange(xRange=x_range, yRange=y_range, padding=0)
            elif sync_x:
                viewbox.setRange(xRange=x_range, padding=0)
            elif sync_y:
                viewbox.setRange(yRange=y_range, padding=0)
        finally:
            # QTimer로 동기화 플래그 리셋 (이벤트 루프 후에)
            QTimer.singleShot(50, self._reset_sync_flag)

    def set_selection(self, indices: list):
        """Highlight selected data points in the plot (ViewSyncManager duck-typing)."""
        self._selected_indices = list(indices)
        # Future: visually highlight the data points at these row indices.
        # For now, just store them. Rendering will be enhanced in a follow-up.

    def get_view_range(self) -> tuple:
        """현재 뷰 범위 반환"""
        if self.plot_widget is None:
            return (None, None)
        viewbox = self.plot_widget.getViewBox()
        rect = viewbox.viewRange()
        return (list(rect[0]), list(rect[1]))

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_view_range_changed(self, viewbox, ranges):
        """ViewBox 범위 변경 처리"""
        if self._is_syncing:
            return  # 동기화 중이면 무시 (무한 루프 방지)

        x_range = list(ranges[0])
        y_range = list(ranges[1])
        self.view_range_changed.emit(self.dataset_id, x_range, y_range)

    def _reset_sync_flag(self):
        """동기화 플래그 리셋"""
        self._is_syncing = False

    def mousePressEvent(self, event):
        """클릭 시 활성화"""
        if event.button() == Qt.LeftButton:
            self.activated.emit(self.dataset_id)
        super().mousePressEvent(event)


class SideBySideLayout(QWidget):
    """
    병렬 비교 레이아웃

    여러 데이터셋을 독립된 패널에 나란히 표시.
    Sync logic delegated to ViewSyncManager (Module H refactor).
    """

    dataset_activated = Signal(str)  # dataset_id

    MAX_PANELS = 4  # 최대 동시 표시 패널 수

    def __init__(self, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.state = state

        self._panels: Dict[str, MiniGraphWidget] = {}

        # ViewSyncManager replaces internal sync logic (Module H)
        self._view_sync_manager = ViewSyncManager(parent=self)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 동기화 옵션
        options_frame = QFrame()
        options_frame.setObjectName("syncOptionsFrame")
        options_layout = QHBoxLayout(options_frame)
        options_layout.setContentsMargins(8, 4, 8, 4)

        options_layout.addWidget(QLabel("Sync:"))

        # Scroll checkbox → controls ViewSyncManager.sync_x
        self.sync_scroll_cb = QCheckBox("Scroll")
        self.sync_scroll_cb.setChecked(self._view_sync_manager.sync_x)
        self.sync_scroll_cb.stateChanged.connect(self._on_sync_scroll_changed)
        options_layout.addWidget(self.sync_scroll_cb)

        # Zoom checkbox → controls ViewSyncManager.sync_y
        self.sync_zoom_cb = QCheckBox("Zoom")
        self.sync_zoom_cb.setChecked(self._view_sync_manager.sync_y)
        self.sync_zoom_cb.stateChanged.connect(self._on_sync_zoom_changed)
        options_layout.addWidget(self.sync_zoom_cb)

        options_layout.addStretch()

        # 리셋 버튼
        self.reset_btn = QPushButton("Reset Views")
        self.reset_btn.setFixedWidth(80)
        self.reset_btn.clicked.connect(self.reset_all_views)
        options_layout.addWidget(self.reset_btn)

        layout.addWidget(options_frame)

        # 패널 스플리터
        self.splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.splitter, 1)

    def _connect_signals(self):
        """시그널 연결"""
        self.state.comparison_settings_changed.connect(self.refresh)
        self.state.dataset_added.connect(self._on_dataset_added)
        self.state.dataset_removed.connect(self._on_dataset_removed)

    # ------------------------------------------------------------------
    # Sync checkbox handlers → delegate to ViewSyncManager
    # ------------------------------------------------------------------

    def _on_sync_scroll_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_x = checked
        self.state.update_comparison_settings(sync_scroll=checked)

    def _on_sync_zoom_changed(self, checkbox_state):
        checked = checkbox_state == Qt.Checked.value if isinstance(checkbox_state, int) else checkbox_state == Qt.Checked
        self._view_sync_manager.sync_y = checked
        self.state.update_comparison_settings(sync_zoom=checked)

    # ------------------------------------------------------------------
    # Dataset lifecycle
    # ------------------------------------------------------------------

    def _on_dataset_added(self, dataset_id: str):
        """데이터셋 추가됨"""
        self.refresh()

    def _on_dataset_removed(self, dataset_id: str):
        """데이터셋 제거됨"""
        if dataset_id in self._panels:
            panel = self._panels[dataset_id]
            self._view_sync_manager.unregister_panel(dataset_id)
            self.splitter.widget(self.splitter.indexOf(panel)).setParent(None)
            del self._panels[dataset_id]

    # ------------------------------------------------------------------
    # Refresh (public API preserved)
    # ------------------------------------------------------------------

    def refresh(self):
        """비교 대상 데이터셋으로 패널 새로고침"""
        # Clear ViewSyncManager and existing panels
        self._view_sync_manager.clear()

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
            # Route view_range_changed through ViewSyncManager
            panel.view_range_changed.connect(
                lambda src_id, xr, yr: self._view_sync_manager.on_source_range_changed(src_id, xr, yr)
            )
            self._panels[dataset_id] = panel
            self._view_sync_manager.register_panel(dataset_id, panel)
            self.splitter.addWidget(panel)

        # 동일 크기로 분할
        if self.splitter.count() > 0:
            sizes = [self.splitter.width() // self.splitter.count()] * self.splitter.count()
            self.splitter.setSizes(sizes)

    # ------------------------------------------------------------------
    # Public API (preserved)
    # ------------------------------------------------------------------

    def reset_all_views(self):
        """모든 패널의 뷰를 자동 범위로 리셋"""
        self._view_sync_manager.reset_all_views()

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """비교 대상 데이터셋 설정"""
        self.state.set_comparison_datasets(dataset_ids[:self.MAX_PANELS])
        self.refresh()

    def sync_all_panels_to(self, source_id: str):
        """특정 패널의 뷰 범위로 모든 패널 동기화 (backward compat)."""
        if source_id not in self._panels:
            return

        source_panel = self._panels[source_id]
        x_range, y_range = source_panel.get_view_range()

        if x_range is None or y_range is None:
            return

        self._view_sync_manager.on_source_range_changed(source_id, x_range, y_range)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_panel_activated(self, dataset_id: str):
        """패널 활성화"""
        self.dataset_activated.emit(dataset_id)
