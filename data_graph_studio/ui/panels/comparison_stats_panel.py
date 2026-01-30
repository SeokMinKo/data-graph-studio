"""
Comparison Statistics Panel - 비교 통계 패널

여러 데이터셋 간의 비교 통계 및 차이 분석 표시
"""

from typing import Optional, List, Dict, Any
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QComboBox, QPushButton, QSizePolicy, QScrollArea,
    QTabWidget
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ...core.data_engine import DataEngine
from ...core.state import (
    AppState, ComparisonMode,
    DIFF_POSITIVE_COLOR, DIFF_NEGATIVE_COLOR, DIFF_NEUTRAL_COLOR
)


class ComparisonStatsPanel(QWidget):
    """
    비교 통계 패널

    Features:
    - 여러 데이터셋의 통계 비교 (mean, sum, min, max 등)
    - 두 데이터셋 간 차이 분석
    - 컬럼별 상세 비교
    """

    column_selected = Signal(str)  # column name

    def __init__(self, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.state = state

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # 탭 위젯
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 탭 1: 기본 통계 비교
        self._setup_stats_tab()

        # 탭 2: 차이 분석
        self._setup_diff_tab()

    def _setup_stats_tab(self):
        """기본 통계 비교 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # 컬럼 선택
        col_layout = QHBoxLayout()
        col_layout.addWidget(QLabel("Column:"))

        self.column_combo = QComboBox()
        self.column_combo.currentTextChanged.connect(self._on_column_changed)
        col_layout.addWidget(self.column_combo, 1)

        layout.addLayout(col_layout)

        # 통계 테이블
        self.stats_table = QTableWidget()
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.verticalHeader().setVisible(False)
        layout.addWidget(self.stats_table)

        self.tab_widget.addTab(tab, "Statistics")

    def _setup_diff_tab(self):
        """차이 분석 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)

        # 데이터셋 선택
        ds_layout = QHBoxLayout()

        ds_layout.addWidget(QLabel("Dataset A:"))
        self.dataset_a_combo = QComboBox()
        ds_layout.addWidget(self.dataset_a_combo, 1)

        ds_layout.addWidget(QLabel("vs"))

        ds_layout.addWidget(QLabel("Dataset B:"))
        self.dataset_b_combo = QComboBox()
        ds_layout.addWidget(self.dataset_b_combo, 1)

        layout.addLayout(ds_layout)

        # 컬럼 선택
        col_layout = QHBoxLayout()
        col_layout.addWidget(QLabel("Value Column:"))
        self.diff_column_combo = QComboBox()
        col_layout.addWidget(self.diff_column_combo, 1)

        col_layout.addWidget(QLabel("Key Column:"))
        self.key_column_combo = QComboBox()
        self.key_column_combo.addItem("(Index)", "")
        col_layout.addWidget(self.key_column_combo, 1)

        layout.addLayout(col_layout)

        # 분석 버튼
        self.analyze_btn = QPushButton("Analyze Difference")
        self.analyze_btn.clicked.connect(self._analyze_difference)
        layout.addWidget(self.analyze_btn)

        # 차이 요약
        self.diff_summary = QLabel("")
        self.diff_summary.setWordWrap(True)
        self.diff_summary.setStyleSheet("padding: 8px; background: #f8f9fa; border-radius: 4px;")
        layout.addWidget(self.diff_summary)

        # 차이 테이블
        self.diff_table = QTableWidget()
        self.diff_table.setAlternatingRowColors(True)
        self.diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.diff_table)

        self.tab_widget.addTab(tab, "Difference")

    def _connect_signals(self):
        """시그널 연결"""
        self.state.comparison_settings_changed.connect(self.refresh)
        self.state.dataset_added.connect(self._update_dataset_combos)
        self.state.dataset_removed.connect(self._update_dataset_combos)

    def refresh(self):
        """패널 새로고침"""
        self._update_column_combos()
        self._update_dataset_combos()
        self._update_stats_table()

    def _update_column_combos(self):
        """컬럼 콤보박스 업데이트"""
        # 공통 숫자 컬럼
        dataset_ids = self.state.comparison_dataset_ids
        if not dataset_ids:
            return

        common_cols = self.engine.get_common_columns(dataset_ids)
        numeric_cols = []

        for col in common_cols:
            # 첫 번째 데이터셋에서 타입 확인
            ds = self.engine.get_dataset(dataset_ids[0])
            if ds and ds.df is not None and col in ds.df.columns:
                dtype = str(ds.df[col].dtype)
                if dtype.startswith(('Int', 'Float', 'UInt')):
                    numeric_cols.append(col)

        # Stats 탭 컬럼 콤보
        current = self.column_combo.currentText()
        self.column_combo.clear()
        self.column_combo.addItems(numeric_cols)
        if current in numeric_cols:
            self.column_combo.setCurrentText(current)

        # Diff 탭 컬럼 콤보
        self.diff_column_combo.clear()
        self.diff_column_combo.addItems(numeric_cols)

        # 키 컬럼 콤보 (모든 공통 컬럼)
        self.key_column_combo.clear()
        self.key_column_combo.addItem("(Index)", "")
        for col in common_cols:
            self.key_column_combo.addItem(col, col)

    def _update_dataset_combos(self, _=None):
        """데이터셋 콤보박스 업데이트"""
        dataset_ids = list(self.state.dataset_metadata.keys())

        # Dataset A
        current_a = self.dataset_a_combo.currentData()
        self.dataset_a_combo.clear()
        for did in dataset_ids:
            metadata = self.state.get_dataset_metadata(did)
            name = metadata.name if metadata else did
            self.dataset_a_combo.addItem(name, did)
        if current_a in dataset_ids:
            idx = dataset_ids.index(current_a)
            self.dataset_a_combo.setCurrentIndex(idx)

        # Dataset B
        current_b = self.dataset_b_combo.currentData()
        self.dataset_b_combo.clear()
        for did in dataset_ids:
            metadata = self.state.get_dataset_metadata(did)
            name = metadata.name if metadata else did
            self.dataset_b_combo.addItem(name, did)
        if current_b in dataset_ids:
            idx = dataset_ids.index(current_b)
            self.dataset_b_combo.setCurrentIndex(idx)
        elif len(dataset_ids) >= 2:
            self.dataset_b_combo.setCurrentIndex(1)

    def _on_column_changed(self, column: str):
        """컬럼 선택 변경"""
        self._update_stats_table()
        self.column_selected.emit(column)

    def _update_stats_table(self):
        """통계 테이블 업데이트"""
        column = self.column_combo.currentText()
        if not column:
            return

        dataset_ids = self.state.comparison_dataset_ids
        if not dataset_ids:
            return

        # 통계 계산
        stats = self.engine.get_comparison_statistics(dataset_ids, column)

        if not stats:
            return

        # 테이블 설정
        stat_names = ["count", "sum", "mean", "median", "std", "min", "max", "q1", "q3"]
        self.stats_table.setColumnCount(len(dataset_ids) + 1)
        self.stats_table.setRowCount(len(stat_names))

        # 헤더
        headers = ["Statistic"] + [stats[did]["name"] for did in dataset_ids if did in stats]
        self.stats_table.setHorizontalHeaderLabels(headers)

        # 데이터
        for row, stat_name in enumerate(stat_names):
            # 통계 이름
            name_item = QTableWidgetItem(stat_name.title())
            name_item.setFlags(name_item.flags() & ~Qt.ItemIsEditable)
            self.stats_table.setItem(row, 0, name_item)

            # 각 데이터셋의 값
            values = []
            for col, did in enumerate(dataset_ids, 1):
                if did in stats:
                    value = stats[did].get(stat_name, None)
                    if value is not None:
                        if isinstance(value, float):
                            text = f"{value:,.2f}"
                        else:
                            text = f"{value:,}"
                        values.append(value)
                    else:
                        text = "-"
                else:
                    text = "-"

                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.stats_table.setItem(row, col, item)

            # 최대값 하이라이트
            if len(values) >= 2 and stat_name not in ["count"]:
                max_val = max(values)
                for col, did in enumerate(dataset_ids, 1):
                    if did in stats:
                        value = stats[did].get(stat_name, None)
                        if value == max_val:
                            item = self.stats_table.item(row, col)
                            item.setBackground(QColor("#e8f5e9"))

    def _analyze_difference(self):
        """차이 분석 실행"""
        dataset_a_id = self.dataset_a_combo.currentData()
        dataset_b_id = self.dataset_b_combo.currentData()
        value_column = self.diff_column_combo.currentText()
        key_column = self.key_column_combo.currentData() or None

        if not dataset_a_id or not dataset_b_id or not value_column:
            return

        if dataset_a_id == dataset_b_id:
            self.diff_summary.setText("Please select different datasets.")
            return

        # 차이 계산
        diff_df = self.engine.calculate_difference(
            dataset_a_id, dataset_b_id, value_column, key_column
        )

        if diff_df is None:
            self.diff_summary.setText("Unable to calculate difference.")
            return

        # 요약 통계
        metadata_a = self.state.get_dataset_metadata(dataset_a_id)
        metadata_b = self.state.get_dataset_metadata(dataset_b_id)
        name_a = metadata_a.name if metadata_a else dataset_a_id
        name_b = metadata_b.name if metadata_b else dataset_b_id

        diff_values = diff_df["diff"].to_numpy()
        positive_count = (diff_values > 0).sum()
        negative_count = (diff_values < 0).sum()
        zero_count = (diff_values == 0).sum()

        import numpy as np
        mean_diff = np.nanmean(diff_values)
        total_diff = np.nansum(diff_values)

        summary_text = f"""
<b>Comparison: {name_a} vs {name_b}</b><br>
<b>Column:</b> {value_column}<br><br>
<b>Total Difference:</b> {total_diff:+,.2f}<br>
<b>Mean Difference:</b> {mean_diff:+,.2f}<br><br>
<b>Positive (A > B):</b> {positive_count} ({positive_count / len(diff_values) * 100:.1f}%)<br>
<b>Negative (A < B):</b> {negative_count} ({negative_count / len(diff_values) * 100:.1f}%)<br>
<b>No Change:</b> {zero_count} ({zero_count / len(diff_values) * 100:.1f}%)
"""
        self.diff_summary.setText(summary_text)

        # 차이 테이블 업데이트
        self._update_diff_table(diff_df, key_column)

    def _update_diff_table(self, diff_df, key_column: str = None):
        """차이 테이블 업데이트"""
        if diff_df is None:
            return

        # 상위 10개 양수/음수 차이
        columns = list(diff_df.columns)
        self.diff_table.setColumnCount(len(columns))
        self.diff_table.setHorizontalHeaderLabels(columns)

        # 크기순 정렬
        import polars as pl
        sorted_df = diff_df.sort("diff", descending=True)

        # 상위 20개만 표시
        max_rows = min(20, len(sorted_df))
        self.diff_table.setRowCount(max_rows)

        for row in range(max_rows):
            for col, col_name in enumerate(columns):
                value = sorted_df[col_name][row]

                if isinstance(value, float):
                    if col_name == "diff_pct":
                        text = f"{value:+.1f}%"
                    else:
                        text = f"{value:+,.2f}" if col_name == "diff" else f"{value:,.2f}"
                else:
                    text = str(value)

                item = QTableWidgetItem(text)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)

                # 색상
                if col_name == "diff":
                    if value > 0:
                        item.setBackground(QColor(DIFF_POSITIVE_COLOR).lighter(170))
                    elif value < 0:
                        item.setBackground(QColor(DIFF_NEGATIVE_COLOR).lighter(170))

                self.diff_table.setItem(row, col, item)
