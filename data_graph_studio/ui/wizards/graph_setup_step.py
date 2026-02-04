"""
Graph Setup Step - Step 2 of New Project Wizard
"""

from __future__ import annotations

import uuid
from typing import List, Optional, Sequence

import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWizardPage,
    QDialog,
    QDialogButtonBox,
)

from data_graph_studio.core.profile import GraphSetting


class ExpandedPreviewDialog(QDialog):
    """Expanded chart preview dialog"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Chart Preview")
        self.setModal(False)
        self.setMinimumSize(800, 600)

        layout = QVBoxLayout(self)
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setBackground("w")
        self.plot_widget.showGrid(x=True, y=True, alpha=0.3)
        layout.addWidget(self.plot_widget)

        button_box = QDialogButtonBox(QDialogButtonBox.Close)
        button_box.rejected.connect(self.close)
        layout.addWidget(button_box)

    def update_plot(self, plot_fn):
        self.plot_widget.clear()
        plot_fn(self.plot_widget)


class GraphSetupStep(QWizardPage):
    """Step 2: Graph basic settings"""

    CHART_TYPES = ["Line", "Bar", "Scatter", "Pie", "Area", "Histogram"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTitle("Step 2: Graph Setup")

        self._columns: List[str] = []
        self._preview_df = None
        self._expanded_dialog: Optional[ExpandedPreviewDialog] = None

        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._update_preview)

        self._build_ui()
        self._connect_signals()

    def _build_ui(self):
        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)

        # Left: Controls
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(10)

        # Chart type
        left_layout.addWidget(QLabel("차트 타입"))
        self.chart_type_combo = QComboBox()
        self.chart_type_combo.setToolTip("Select chart visualization type")
        self.chart_type_combo.addItems(self.CHART_TYPES)
        left_layout.addWidget(self.chart_type_combo)

        # X axis
        left_layout.addWidget(QLabel("X축 컬럼 *"))
        self.x_column_combo = QComboBox()
        self.x_column_combo.setToolTip("Column to use as X-axis values")
        left_layout.addWidget(self.x_column_combo)

        # Y axis (multi) with search
        left_layout.addWidget(QLabel("Y축 컬럼 * (복수 선택)"))
        self.y_search_edit = QLineEdit()
        self.y_search_edit.setPlaceholderText("🔍 Search Y columns...")
        self.y_search_edit.setClearButtonEnabled(True)
        self.y_search_edit.textChanged.connect(self._filter_y_columns)
        left_layout.addWidget(self.y_search_edit)
        self.y_columns_list = QListWidget()
        self.y_columns_list.setToolTip("Check columns to plot on Y-axis")
        self.y_columns_list.setSelectionMode(QListWidget.NoSelection)
        left_layout.addWidget(self.y_columns_list)

        # Group column
        left_layout.addWidget(QLabel("Group 컬럼"))
        self.group_column_combo = QComboBox()
        self.group_column_combo.setToolTip("Column to group data by (creates separate series)")
        left_layout.addWidget(self.group_column_combo)

        # Hover columns with search
        left_layout.addWidget(QLabel("Hover 컬럼 (복수 선택)"))
        self.hover_search_edit = QLineEdit()
        self.hover_search_edit.setPlaceholderText("🔍 Search Hover columns...")
        self.hover_search_edit.setClearButtonEnabled(True)
        self.hover_search_edit.textChanged.connect(self._filter_hover_columns)
        left_layout.addWidget(self.hover_search_edit)
        self.hover_columns_list = QListWidget()
        self.hover_columns_list.setToolTip("Check columns to show in hover tooltip")
        self.hover_columns_list.setSelectionMode(QListWidget.NoSelection)
        left_layout.addWidget(self.hover_columns_list)

        left_layout.addStretch(1)

        # Right: Preview
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        preview_header = QHBoxLayout()
        preview_header.addWidget(QLabel("미리보기 차트"))
        preview_header.addStretch(1)
        self.expand_button = QToolButton()
        self.expand_button.setText("🔍")
        self.expand_button.setToolTip("확대 보기")
        preview_header.addWidget(self.expand_button)
        right_layout.addLayout(preview_header)

        self.preview_plot = pg.PlotWidget()
        self.preview_plot.setBackground("w")
        self.preview_plot.showGrid(x=True, y=True, alpha=0.3)
        right_layout.addWidget(self.preview_plot)

        main_layout.addWidget(left_panel, 1)
        main_layout.addWidget(right_panel, 2)

    def _connect_signals(self):
        self.chart_type_combo.currentIndexChanged.connect(self._schedule_preview_update)
        self.x_column_combo.currentIndexChanged.connect(self._schedule_preview_update)
        self.group_column_combo.currentIndexChanged.connect(self._schedule_preview_update)
        self.y_columns_list.itemChanged.connect(self._schedule_preview_update)
        self.hover_columns_list.itemChanged.connect(self._schedule_preview_update)
        self.expand_button.clicked.connect(self._open_expanded_preview)

    # ---------- Wizard hooks ----------

    def initializePage(self):
        """Load columns from previous step"""
        wizard = self.wizard()
        if wizard is None:
            return

        parsing_step = wizard.page(0)
        if parsing_step and hasattr(parsing_step, "get_preview_df"):
            self._preview_df = parsing_step.get_preview_df()
            if self._preview_df is not None and hasattr(self._preview_df, "columns"):
                self._columns = list(self._preview_df.columns)
            else:
                self._columns = []
        else:
            self._columns = []

        self._populate_columns()
        self._schedule_preview_update()

    def validatePage(self) -> bool:
        """X axis + at least one Y axis required"""
        x_col = self._get_selected_x_column()
        y_cols = self._get_selected_y_columns()
        return bool(x_col) and len(y_cols) >= 1

    # ---------- Public API ----------

    def get_graph_setting(self) -> GraphSetting:
        """Return GraphSetting from current UI state"""
        wizard = self.wizard()
        dataset_id = getattr(wizard, "dataset_id", "") if wizard else ""

        x_col = self._get_selected_x_column()
        y_cols = tuple(self._get_selected_y_columns())
        group_col = self._get_selected_group_column()
        hover_cols = tuple(self._get_selected_hover_columns())

        return GraphSetting(
            id=str(uuid.uuid4()),
            name="Profile_1",
            dataset_id=dataset_id,
            chart_type=self.chart_type_combo.currentText(),
            x_column=x_col,
            group_columns=(group_col,) if group_col else (),
            value_columns=y_cols,
            hover_columns=hover_cols,
            chart_settings={},
        )

    # ---------- Internal helpers ----------

    def _populate_columns(self):
        self.x_column_combo.blockSignals(True)
        self.group_column_combo.blockSignals(True)
        try:
            self.x_column_combo.clear()
            self.x_column_combo.addItem("선택...")
            self.x_column_combo.addItems(self._columns)

            self.group_column_combo.clear()
            self.group_column_combo.addItem("(없음)")
            self.group_column_combo.addItems(self._columns)

            self.y_columns_list.clear()
            for col in self._columns:
                item = QListWidgetItem(col)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.y_columns_list.addItem(item)

            self.hover_columns_list.clear()
            for col in self._columns:
                item = QListWidgetItem(col)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Unchecked)
                self.hover_columns_list.addItem(item)
        finally:
            self.x_column_combo.blockSignals(False)
            self.group_column_combo.blockSignals(False)

    def _filter_y_columns(self, text: str):
        """Filter Y columns list by search text (preserves check state)"""
        self._filter_list_widget(self.y_columns_list, text)

    def _filter_hover_columns(self, text: str):
        """Filter Hover columns list by search text (preserves check state)"""
        self._filter_list_widget(self.hover_columns_list, text)

    @staticmethod
    def _filter_list_widget(list_widget: QListWidget, text: str):
        """Show/hide items based on search text (case-insensitive)"""
        search = text.strip().lower()
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if not search:
                item.setHidden(False)
            else:
                item.setHidden(search not in item.text().lower())

    def _get_selected_x_column(self) -> Optional[str]:
        value = self.x_column_combo.currentText()
        if not value or value == "선택...":
            return None
        return value

    def _get_selected_group_column(self) -> Optional[str]:
        value = self.group_column_combo.currentText()
        if not value or value == "(없음)":
            return None
        return value

    def _get_selected_y_columns(self) -> List[str]:
        return self._get_checked_items(self.y_columns_list)

    def _get_selected_hover_columns(self) -> List[str]:
        return self._get_checked_items(self.hover_columns_list)

    @staticmethod
    def _get_checked_items(list_widget: QListWidget) -> List[str]:
        values = []
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item.checkState() == Qt.Checked:
                values.append(item.text())
        return values

    def _schedule_preview_update(self):
        self._debounce_timer.start()

    def _open_expanded_preview(self):
        if self._expanded_dialog is None:
            self._expanded_dialog = ExpandedPreviewDialog(self)
        self._expanded_dialog.show()
        self._expanded_dialog.raise_()
        self._expanded_dialog.activateWindow()
        self._expanded_dialog.update_plot(self._plot_preview)

    # ---------- Plotting ----------

    def _update_preview(self):
        self.preview_plot.clear()
        self._plot_preview(self.preview_plot)
        if self._expanded_dialog and self._expanded_dialog.isVisible():
            self._expanded_dialog.update_plot(self._plot_preview)

    def _plot_preview(self, plot_widget):
        chart_type = self.chart_type_combo.currentText()
        x_col = self._get_selected_x_column()
        y_cols = self._get_selected_y_columns()

        if not x_col or not y_cols or self._preview_df is None:
            return

        x_data = self._extract_series(self._preview_df, x_col)
        if x_data is None:
            return

        if chart_type == "Histogram":
            y_data = self._extract_series(self._preview_df, y_cols[0])
            if y_data is None:
                return
            hist, bin_edges = np.histogram(y_data[~np.isnan(y_data)], bins=30)
            plot_widget.plot(bin_edges, hist, stepMode="center", fillLevel=0,
                             brush=(31, 119, 180, 150), pen=pg.mkPen((31, 119, 180)))
            return

        if chart_type == "Pie":
            y_data = self._extract_series(self._preview_df, y_cols[0])
            if y_data is None:
                return
            try:
                from pyqtgraph.graphicsItems.PieChartItem import PieChartItem
                values = np.array(y_data)
                values = values[~np.isnan(values)]
                if len(values) == 0:
                    return
                pie = PieChartItem(values.tolist())
                plot_widget.addItem(pie)
                plot_widget.setAspectLocked(True)
                plot_widget.hideAxis('bottom')
                plot_widget.hideAxis('left')
            except Exception:
                indices = np.arange(len(y_data))
                plot_widget.plot(indices, y_data, pen=None, symbol='o')
            return

        # Common charts
        for i, y_col in enumerate(y_cols):
            y_data = self._extract_series(self._preview_df, y_col)
            if y_data is None:
                continue
            if chart_type == "Scatter":
                plot_widget.plot(x_data, y_data, pen=None, symbol='o')
            elif chart_type == "Bar":
                x_idx = np.arange(len(y_data))
                bar = pg.BarGraphItem(x=x_idx, height=y_data, width=0.6, brush=(31, 119, 180, 180))
                plot_widget.addItem(bar)
            elif chart_type == "Area":
                plot_widget.plot(x_data, y_data, pen=pg.mkPen(width=2), fillLevel=0, brush=(31, 119, 180, 100))
            else:  # Line default
                plot_widget.plot(x_data, y_data, pen=pg.mkPen(width=2))

    @staticmethod
    def _extract_series(df, column: str) -> Optional[np.ndarray]:
        try:
            # Get raw series first
            if hasattr(df, "to_pandas"):
                raw = df[column].to_pandas()
            elif hasattr(df, "__class__") and df.__class__.__name__.lower().startswith("dataframe"):
                raw = df[column]
            elif hasattr(df, "__getitem__"):
                series = df[column]
                if hasattr(series, "to_list"):
                    raw_list = series.to_list()
                    try:
                        return np.array(raw_list, dtype=float)
                    except (ValueError, TypeError):
                        return np.arange(len(raw_list), dtype=float)
                return None
            else:
                return None
            
            # Try numeric conversion
            try:
                import pandas as pd
                numeric = pd.to_numeric(raw, errors='coerce')
                result = numeric.to_numpy(dtype=float)
                # If all NaN, use index instead
                if np.all(np.isnan(result)):
                    return np.arange(len(raw), dtype=float)
                return result
            except Exception:
                return np.arange(len(raw), dtype=float)
        except Exception:
            return None
        return None
