"""
Graph Panel - 메인 그래프 + 옵션 + 통계 차트
"""

from typing import Optional, List, Dict, Any
import numpy as np

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QComboBox, QSpinBox, QDoubleSpinBox, QCheckBox,
    QScrollArea, QSplitter, QToolButton, QButtonGroup,
    QSizePolicy, QGroupBox, QDialog, QDialogButtonBox
)
from PySide6.QtCore import Qt, Signal, Slot
from PySide6.QtGui import QMouseEvent

import pyqtgraph as pg


class ExpandedChartDialog(QDialog):
    """확대된 차트를 보여주는 다이얼로그"""
    
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumSize(800, 600)
        self.resize(1000, 700)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # 큰 그래프 위젯
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground('w')
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        self.plot_widget.setLabel('left', '')
        self.plot_widget.setLabel('bottom', '')
        layout.addWidget(self.plot_widget)
        
        # 닫기 버튼
        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)
    
    def plot_histogram(self, data: np.ndarray, title: str, color: tuple):
        """히스토그램 그리기"""
        self.setWindowTitle(title)
        self.plot_widget.clear()
        
        if data is not None and len(data) > 0:
            try:
                clean_data = data[~np.isnan(data)]
                hist, bins = np.histogram(clean_data, bins=50)
                self.plot_widget.plot(bins, hist, stepMode=True, fillLevel=0, 
                                      brush=color, pen=pg.mkPen(color[:3], width=1))
                self.plot_widget.setLabel('bottom', 'Value')
                self.plot_widget.setLabel('left', 'Frequency')
                
                # 통계 정보 추가
                mean_val = np.mean(clean_data)
                median_val = np.median(clean_data)
                std_val = np.std(clean_data)
                
                # 평균선 추가
                self.plot_widget.addLine(x=mean_val, pen=pg.mkPen('r', width=2, style=Qt.DashLine))
                
                # 범례 텍스트
                stats_text = f"Mean: {mean_val:.2f}\nMedian: {median_val:.2f}\nStd: {std_val:.2f}"
                text_item = pg.TextItem(stats_text, anchor=(0, 0), color='k')
                text_item.setPos(bins[0], max(hist) * 0.9)
                self.plot_widget.addItem(text_item)
            except Exception as e:
                print(f"Error plotting histogram: {e}")


class ClickablePlotWidget(pg.PlotWidget):
    """더블클릭 가능한 PlotWidget"""
    
    double_clicked = Signal()
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._data = None
        self._title = ""
        self._color = (100, 100, 200, 100)
    
    def set_data(self, data: np.ndarray, title: str, color: tuple):
        """데이터 저장 (확대 시 사용)"""
        self._data = data
        self._title = title
        self._color = color
    
    def mouseDoubleClickEvent(self, event: QMouseEvent):
        """더블클릭 시 확대 창 열기"""
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit()
            self._show_expanded()
        super().mouseDoubleClickEvent(event)
    
    def _show_expanded(self):
        """확대 창 표시"""
        if self._data is None:
            return
        
        dialog = ExpandedChartDialog(self._title, self)
        dialog.plot_histogram(self._data, self._title, self._color)
        dialog.exec()

from ...core.state import AppState, ChartType, ToolMode
from ...core.data_engine import DataEngine


class GraphOptionsPanel(QFrame):
    """Modern Graph Options Panel"""
    
    option_changed = Signal()
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("GraphOptionsPanel")
        self.setFixedWidth(220)
        
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #GraphOptionsPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FAFAFA, stop:1 #F5F5F5);
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
            QGroupBox {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                margin-top: 12px;
                padding: 12px;
                font-weight: 600;
                font-size: 11px;
                color: #6B7280;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background: white;
                color: #374151;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
            QComboBox, QSpinBox, QDoubleSpinBox {
                background: #F9FAFB;
                border: 1px solid #E5E7EB;
                border-radius: 6px;
                padding: 6px 10px;
                color: #374151;
            }
            QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {
                border-color: #6366F1;
            }
            QCheckBox {
                color: #374151;
                font-size: 12px;
            }
            QLabel {
                color: #6B7280;
                font-size: 11px;
                background: transparent;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        
        # Panel title
        title = QLabel("⚙️ Chart Options")
        title.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #111827;
            background: transparent;
            padding: 4px 0;
        """)
        layout.addWidget(title)
        
        # X-Axis section
        x_group = QGroupBox("X-Axis")
        x_layout = QVBoxLayout(x_group)
        
        self.x_column_combo = QComboBox()
        self.x_column_combo.currentTextChanged.connect(self._on_x_column_changed)
        x_layout.addWidget(self.x_column_combo)
        
        self.x_log_check = QCheckBox("Log Scale")
        self.x_log_check.stateChanged.connect(self._on_option_changed)
        x_layout.addWidget(self.x_log_check)
        
        layout.addWidget(x_group)
        
        # Chart Type
        type_group = QGroupBox("Chart Type")
        type_layout = QVBoxLayout(type_group)
        
        self.chart_type_combo = QComboBox()
        for ct in ChartType:
            self.chart_type_combo.addItem(ct.value.title(), ct)
        self.chart_type_combo.currentIndexChanged.connect(self._on_chart_type_changed)
        type_layout.addWidget(self.chart_type_combo)
        
        layout.addWidget(type_group)
        
        # Style
        style_group = QGroupBox("Style")
        style_layout = QVBoxLayout(style_group)
        
        # Line Width
        lw_layout = QHBoxLayout()
        lw_layout.addWidget(QLabel("Line Width:"))
        self.line_width_spin = QSpinBox()
        self.line_width_spin.setRange(1, 10)
        self.line_width_spin.setValue(2)
        self.line_width_spin.valueChanged.connect(self._on_option_changed)
        lw_layout.addWidget(self.line_width_spin)
        style_layout.addLayout(lw_layout)
        
        # Marker Size
        ms_layout = QHBoxLayout()
        ms_layout.addWidget(QLabel("Marker Size:"))
        self.marker_size_spin = QSpinBox()
        self.marker_size_spin.setRange(0, 20)
        self.marker_size_spin.setValue(6)
        self.marker_size_spin.valueChanged.connect(self._on_option_changed)
        ms_layout.addWidget(self.marker_size_spin)
        style_layout.addLayout(ms_layout)
        
        # Fill Opacity
        fo_layout = QHBoxLayout()
        fo_layout.addWidget(QLabel("Fill Opacity:"))
        self.fill_opacity_spin = QDoubleSpinBox()
        self.fill_opacity_spin.setRange(0, 1)
        self.fill_opacity_spin.setSingleStep(0.1)
        self.fill_opacity_spin.setValue(0.3)
        self.fill_opacity_spin.valueChanged.connect(self._on_option_changed)
        fo_layout.addWidget(self.fill_opacity_spin)
        style_layout.addLayout(fo_layout)
        
        # Show Data Labels
        self.show_labels_check = QCheckBox("Show Data Labels")
        self.show_labels_check.stateChanged.connect(self._on_option_changed)
        style_layout.addWidget(self.show_labels_check)
        
        layout.addWidget(style_group)
        
        layout.addStretch()
    
    def _on_x_column_changed(self, column: str):
        self.state.set_x_column(column if column else None)
    
    def _on_chart_type_changed(self, index: int):
        chart_type = self.chart_type_combo.currentData()
        if chart_type:
            self.state.set_chart_type(chart_type)
    
    def _on_option_changed(self):
        self.state.update_chart_settings(
            line_width=self.line_width_spin.value(),
            marker_size=self.marker_size_spin.value(),
            fill_opacity=self.fill_opacity_spin.value(),
            show_data_labels=self.show_labels_check.isChecked(),
            x_log_scale=self.x_log_check.isChecked()
        )
        self.option_changed.emit()
    
    def set_columns(self, columns: List[str]):
        """컬럼 목록 설정"""
        self.x_column_combo.clear()
        self.x_column_combo.addItem("")  # 빈 선택
        self.x_column_combo.addItems(columns)


class StatPanel(QFrame):
    """Modern Statistics Panel with mini charts"""
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("StatPanel")
        self.setFixedWidth(220)
        
        # Current data
        self._x_data: Optional[np.ndarray] = None
        self._y_data: Optional[np.ndarray] = None
        
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        self.setStyleSheet("""
            #StatPanel {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 #FAFAFA, stop:1 #F5F5F5);
                border: 1px solid #E5E7EB;
                border-radius: 12px;
            }
            QGroupBox {
                background: white;
                border: 1px solid #E5E7EB;
                border-radius: 10px;
                margin-top: 12px;
                padding: 8px;
                font-weight: 600;
                font-size: 11px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
                background: white;
                color: #374151;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }
        """)
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        
        # Panel title
        title = QLabel("📈 Statistics")
        title.setStyleSheet("""
            font-weight: 600;
            font-size: 13px;
            color: #111827;
            background: transparent;
            padding: 4px 0;
        """)
        layout.addWidget(title)
        
        # X-Axis Distribution
        x_group = QGroupBox("X Distribution")
        x_group.setToolTip("Double-click to expand")
        x_layout = QVBoxLayout(x_group)
        
        self.x_hist_widget = ClickablePlotWidget()
        self.x_hist_widget.setMaximumHeight(100)
        self.x_hist_widget.setBackground('w')
        self.x_hist_widget.hideAxis('bottom')
        self.x_hist_widget.hideAxis('left')
        self.x_hist_widget.setCursor(Qt.PointingHandCursor)
        x_layout.addWidget(self.x_hist_widget)
        
        layout.addWidget(x_group)
        
        # Y-Axis Distribution (더블클릭 가능)
        y_group = QGroupBox("Y Distribution")
        y_group.setToolTip("Double-click to expand")
        y_layout = QVBoxLayout(y_group)
        
        self.y_hist_widget = ClickablePlotWidget()
        self.y_hist_widget.setMaximumHeight(100)
        self.y_hist_widget.setBackground('w')
        self.y_hist_widget.hideAxis('bottom')
        self.y_hist_widget.hideAxis('left')
        self.y_hist_widget.setCursor(Qt.PointingHandCursor)
        y_layout.addWidget(self.y_hist_widget)
        
        layout.addWidget(y_group)
        
        # Summary Stats
        stats_group = QGroupBox("Statistics")
        stats_layout = QVBoxLayout(stats_group)
        
        self.stats_label = QLabel("No data")
        self.stats_label.setStyleSheet("font-family: monospace; font-size: 10px;")
        self.stats_label.setWordWrap(True)
        stats_layout.addWidget(self.stats_label)
        
        layout.addWidget(stats_group)
        
        layout.addStretch()
    
    def update_histograms(self, x_data: Optional[np.ndarray], y_data: Optional[np.ndarray]):
        """히스토그램 업데이트"""
        # 데이터 저장
        self._x_data = x_data
        self._y_data = y_data
        
        # X Histogram
        self.x_hist_widget.clear()
        if x_data is not None and len(x_data) > 0:
            try:
                clean_x = x_data[~np.isnan(x_data)]
                hist, bins = np.histogram(clean_x, bins=30)
                self.x_hist_widget.plot(bins, hist, stepMode=True, fillLevel=0, 
                                        brush=(100, 100, 200, 100))
                self.x_hist_widget.set_data(x_data, "X-Axis Distribution", (100, 100, 200, 150))
            except:
                pass
        
        # Y Histogram
        self.y_hist_widget.clear()
        if y_data is not None and len(y_data) > 0:
            try:
                clean_y = y_data[~np.isnan(y_data)]
                hist, bins = np.histogram(clean_y, bins=30)
                self.y_hist_widget.plot(bins, hist, stepMode=True, fillLevel=0,
                                        brush=(100, 200, 100, 100))
                self.y_hist_widget.set_data(y_data, "Y-Axis Distribution", (100, 200, 100, 150))
            except:
                pass
    
    def update_stats(self, stats: Dict[str, Any]):
        """통계 업데이트"""
        if not stats:
            self.stats_label.setText("No data")
            return
        
        lines = []
        for key, value in stats.items():
            if isinstance(value, float):
                lines.append(f"{key}: {value:.2f}")
            else:
                lines.append(f"{key}: {value}")
        
        self.stats_label.setText("\n".join(lines))


class MainGraph(pg.PlotWidget):
    """메인 그래프 위젯"""
    
    points_selected = Signal(list)  # 선택된 포인트 인덱스
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        
        # 설정
        self.setBackground('w')
        self.showGrid(x=True, y=True, alpha=0.3)
        self.setLabel('left', '')
        self.setLabel('bottom', '')
        
        # Legend
        self.legend = self.addLegend()
        
        # 데이터
        self._plot_items = []
        self._scatter_items = []
        self._data_x = None
        self._data_y = None
        
        # 선택 영역
        self._selection_rect = None
        self._lasso_points = []
        
        # 마우스 이벤트
        self.scene().sigMouseClicked.connect(self._on_mouse_clicked)
    
    def plot_data(
        self,
        x_data: np.ndarray,
        y_data: np.ndarray,
        groups: Optional[Dict[str, np.ndarray]] = None,
        chart_type: ChartType = ChartType.LINE,
        settings: Optional[Dict] = None
    ):
        """데이터 플롯"""
        self.clear_plot()
        
        self._data_x = x_data
        self._data_y = y_data
        
        settings = settings or {}
        line_width = settings.get('line_width', 2)
        marker_size = settings.get('marker_size', 6)
        
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
                  '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']
        
        if groups:
            # 그룹별 플롯
            for i, (group_name, mask) in enumerate(groups.items()):
                color = colors[i % len(colors)]
                self._plot_series(
                    x_data[mask], y_data[mask], 
                    chart_type, color, group_name,
                    line_width, marker_size
                )
        else:
            # 단일 플롯
            self._plot_series(
                x_data, y_data,
                chart_type, colors[0], None,
                line_width, marker_size
            )
    
    def _plot_series(
        self,
        x: np.ndarray,
        y: np.ndarray,
        chart_type: ChartType,
        color: str,
        name: Optional[str],
        line_width: int,
        marker_size: int
    ):
        """시리즈 플롯"""
        pen = pg.mkPen(color=color, width=line_width)
        brush = pg.mkBrush(color=color)
        
        if chart_type == ChartType.LINE:
            item = self.plot(x, y, pen=pen, name=name)
            if marker_size > 0:
                scatter = pg.ScatterPlotItem(x, y, size=marker_size, brush=brush)
                self.addItem(scatter)
                self._scatter_items.append(scatter)
                
        elif chart_type == ChartType.SCATTER:
            scatter = pg.ScatterPlotItem(x, y, size=marker_size, brush=brush, name=name)
            self.addItem(scatter)
            self._scatter_items.append(scatter)
            item = scatter
            
        elif chart_type == ChartType.BAR:
            # 바 차트 (BarGraphItem)
            width = (x.max() - x.min()) / len(x) * 0.8 if len(x) > 1 else 0.8
            item = pg.BarGraphItem(x=x, height=y, width=width, brush=brush, name=name)
            self.addItem(item)
            
        elif chart_type == ChartType.AREA:
            # colorTuple 대신 mkBrush 사용 (투명도 적용)
            fill_brush = pg.mkBrush(color=color)
            fill_brush.setColor(pg.mkColor(color).lighter(150))
            fill_brush.color().setAlpha(50)
            item = self.plot(x, y, pen=pen, fillLevel=0, brush=fill_brush, name=name)
            
        else:
            item = self.plot(x, y, pen=pen, name=name)
        
        self._plot_items.append(item)
    
    def clear_plot(self):
        """플롯 클리어"""
        for item in self._plot_items:
            self.removeItem(item)
        for item in self._scatter_items:
            self.removeItem(item)
        self._plot_items.clear()
        self._scatter_items.clear()
        self._data_x = None
        self._data_y = None
    
    def reset_view(self):
        """뷰 리셋"""
        self.autoRange()
    
    def _on_mouse_clicked(self, event):
        """마우스 클릭 이벤트"""
        if self.state.tool_mode in [ToolMode.RECT_SELECT, ToolMode.LASSO_SELECT]:
            # 선택 모드
            pos = event.scenePos()
            mouse_point = self.plotItem.vb.mapSceneToView(pos)
            
            # TODO: 선택 로직 구현
            pass


class GraphPanel(QWidget):
    """
    Graph Panel
    
    구조:
    ┌────────────┬─────────────────────────────┬────────────┐
    │  Options   │         Main Graph          │   Stats    │
    │  (200px)   │                             │  (200px)   │
    └────────────┴─────────────────────────────┴────────────┘
    """
    
    def __init__(self, state: AppState, engine: DataEngine):
        super().__init__()
        self.state = state
        self.engine = engine
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 스플리터
        splitter = QSplitter(Qt.Horizontal)
        
        # 옵션 패널 (왼쪽)
        self.options_panel = GraphOptionsPanel(self.state)
        splitter.addWidget(self.options_panel)
        
        # 메인 그래프 (중앙)
        self.main_graph = MainGraph(self.state)
        splitter.addWidget(self.main_graph)
        
        # 통계 패널 (오른쪽)
        self.stat_panel = StatPanel(self.state)
        splitter.addWidget(self.stat_panel)
        
        # 스플리터 비율
        splitter.setSizes([200, 600, 200])
        splitter.setStretchFactor(0, 0)  # Options: 고정
        splitter.setStretchFactor(1, 1)  # Graph: 확장
        splitter.setStretchFactor(2, 0)  # Stats: 고정
        
        layout.addWidget(splitter)
    
    def _connect_signals(self):
        self.state.chart_settings_changed.connect(self.refresh)
        self.state.group_zone_changed.connect(self.refresh)
        self.state.value_zone_changed.connect(self.refresh)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.options_panel.option_changed.connect(self.refresh)
    
    def refresh(self):
        """Refresh graph with grouping support"""
        if not self.engine.is_loaded:
            return
        
        # X column
        x_col = self.state.x_column
        if not x_col:
            x_data = np.arange(self.engine.row_count)
        else:
            x_data = self.engine.df[x_col].to_numpy()
        
        # Y column (first value column)
        if self.state.value_columns:
            value_col = self.state.value_columns[0]
            y_col_name = value_col.name
        else:
            # First numeric column
            numeric_cols = [
                col for col in self.engine.columns
                if self.engine.dtypes.get(col, '').startswith(('Int', 'Float'))
            ]
            if numeric_cols:
                y_col_name = numeric_cols[0]
            else:
                return
        
        y_data = self.engine.df[y_col_name].to_numpy()
        
        # Plot settings
        settings = {
            'line_width': self.state.chart_settings.line_width,
            'marker_size': self.state.chart_settings.marker_size,
            'fill_opacity': self.state.chart_settings.fill_opacity,
        }
        
        # Check for grouping
        groups = None
        if self.state.group_columns:
            groups = self._build_group_masks()
        
        self.main_graph.plot_data(
            x_data, y_data,
            groups=groups,
            chart_type=self.state.chart_settings.chart_type,
            settings=settings
        )
        
        # 히스토그램 업데이트
        self.stat_panel.update_histograms(x_data, y_data)
        
        # 통계 업데이트
        if self.state.value_columns:
            stats = self.engine.get_statistics(self.state.value_columns[0].name)
            self.stat_panel.update_stats(stats)
    
    def _on_selection_changed(self):
        """Handle selection change"""
        # TODO: Highlight selected points
        pass
    
    def _build_group_masks(self) -> Dict[str, np.ndarray]:
        """
        Build group masks for plotting each group with different color
        
        Returns: {group_name: boolean_mask_array}
        """
        if not self.state.group_columns or not self.engine.is_loaded:
            return None
        
        df = self.engine.df
        n_rows = len(df)
        
        # Get group column names
        group_cols = [g.name for g in self.state.group_columns]
        
        # Build combined group key for each row
        groups = {}
        
        if len(group_cols) == 1:
            # Single group column
            col = group_cols[0]
            unique_values = df[col].unique().sort().to_list()
            
            for val in unique_values:
                group_name = str(val) if val is not None else "(Empty)"
                mask = (df[col] == val).to_numpy()
                groups[group_name] = mask
        else:
            # Multiple group columns - combine keys
            # Create a compound key column
            combined = df.select(group_cols)
            
            # Get unique combinations
            unique_combos = combined.unique().sort(group_cols)
            
            for row in unique_combos.iter_rows():
                # Build group name
                parts = [str(v) if v is not None else "(Empty)" for v in row]
                group_name = " / ".join(parts)
                
                # Build mask for this combination
                mask = np.ones(n_rows, dtype=bool)
                for col, val in zip(group_cols, row):
                    if val is None:
                        mask &= df[col].is_null().to_numpy()
                    else:
                        mask &= (df[col] == val).to_numpy()
                
                groups[group_name] = mask
        
        return groups
    
    def reset_view(self):
        """뷰 리셋"""
        self.main_graph.reset_view()
    
    def autofit(self):
        """자동 맞춤"""
        self.main_graph.autoRange()
    
    def export_image(self, path: str):
        """이미지 내보내기"""
        from PySide6.QtGui import QImage, QPainter
        from PySide6.QtWidgets import QApplication
        
        # 현재 그래프를 이미지로
        exporter = pg.exporters.ImageExporter(self.main_graph.plotItem)
        exporter.export(path)
    
    def clear(self):
        """클리어"""
        self.main_graph.clear_plot()
        self.stat_panel.update_histograms(None, None)
        self.stat_panel.update_stats({})
    
    def set_columns(self, columns: List[str]):
        """컬럼 목록 설정"""
        self.options_panel.set_columns(columns)
