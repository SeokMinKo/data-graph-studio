"""
Comparison Statistics Panel - 비교 통계 패널

여러 데이터셋 간의 비교 통계 및 차이 분석 표시
통계 검정 (t-test, correlation, p-value) 포함
"""

import logging
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox,
    QComboBox, QPushButton, QTabWidget, QTextEdit, QFileDialog
)

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont

from ...core.data_engine import DataEngine
from ...core.state import (
    AppState, DIFF_POSITIVE_COLOR, DIFF_NEGATIVE_COLOR
)
from ..adapters.app_state_adapter import AppStateAdapter


logger = logging.getLogger(__name__)

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
        self._state_adapter = AppStateAdapter(state, parent=self)
        self._is_light: bool = False  # Default: dark (midnight) theme

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # 탭 위젯 - compact style
        self.tab_widget = QTabWidget()
        layout.addWidget(self.tab_widget)

        # 탭 1: 기본 통계 비교
        self._setup_stats_tab()

        # 탭 2: 통계 검정
        self._setup_test_tab()

        # 탭 3: 차이 분석
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
        self.column_combo.setToolTip("Select column to compare statistics")
        self.column_combo.currentTextChanged.connect(self._on_column_changed)
        col_layout.addWidget(self.column_combo, 1)

        layout.addLayout(col_layout)

        # 통계 테이블
        self.stats_table = QTableWidget()
        self.stats_table.setAlternatingRowColors(True)
        self.stats_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.stats_table.verticalHeader().setVisible(False)
        layout.addWidget(self.stats_table)

        # Export CSV button
        export_stats_btn = QPushButton("Export CSV")
        export_stats_btn.setToolTip("Export statistics table to CSV")
        export_stats_btn.clicked.connect(self._export_stats_csv)
        layout.addWidget(export_stats_btn)

        self.tab_widget.addTab(tab, "Statistics")

    def _setup_test_tab(self):
        """통계 검정 탭"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # 데이터셋 선택
        ds_group = QGroupBox("Datasets")
        ds_layout = QHBoxLayout(ds_group)

        ds_layout.addWidget(QLabel("Dataset A:"))
        self.test_dataset_a = QComboBox()
        ds_layout.addWidget(self.test_dataset_a, 1)

        ds_layout.addWidget(QLabel("Dataset B:"))
        self.test_dataset_b = QComboBox()
        ds_layout.addWidget(self.test_dataset_b, 1)

        layout.addWidget(ds_group)

        # 컬럼 및 검정 유형 선택
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)

        col_layout = QHBoxLayout()
        col_layout.addWidget(QLabel("Value Column:"))
        self.test_column_combo = QComboBox()
        col_layout.addWidget(self.test_column_combo, 1)
        options_layout.addLayout(col_layout)

        test_layout = QHBoxLayout()
        test_layout.addWidget(QLabel("Test Type:"))
        self.test_type_combo = QComboBox()
        self.test_type_combo.setToolTip("Select statistical test method")
        self.test_type_combo.addItem("Auto (recommended)", "auto")
        self.test_type_combo.addItem("t-test (parametric)", "ttest")
        self.test_type_combo.addItem("Mann-Whitney U (non-parametric)", "mannwhitney")
        self.test_type_combo.addItem("Kolmogorov-Smirnov", "ks")
        test_layout.addWidget(self.test_type_combo, 1)
        options_layout.addLayout(test_layout)

        corr_layout = QHBoxLayout()
        corr_layout.addWidget(QLabel("Correlation:"))
        self.corr_method_combo = QComboBox()
        self.corr_method_combo.setToolTip("Select correlation calculation method")
        self.corr_method_combo.addItem("Pearson", "pearson")
        self.corr_method_combo.addItem("Spearman", "spearman")
        corr_layout.addWidget(self.corr_method_combo, 1)
        options_layout.addLayout(corr_layout)

        layout.addWidget(options_group)

        # 분석 버튼
        btn_layout = QHBoxLayout()
        self.run_test_btn = QPushButton("Run Statistical Test")
        self.run_test_btn.setToolTip("Run statistical test")
        self.run_test_btn.clicked.connect(self._run_statistical_test)
        btn_layout.addWidget(self.run_test_btn)

        self.run_corr_btn = QPushButton("Calculate Correlation")
        self.run_corr_btn.setToolTip("Run correlation analysis")
        self.run_corr_btn.clicked.connect(self._run_correlation)
        btn_layout.addWidget(self.run_corr_btn)

        layout.addLayout(btn_layout)

        # 결과 표시
        results_group = QGroupBox("Results")
        results_layout = QVBoxLayout(results_group)

        self.test_results = QTextEdit()
        self.test_results.setReadOnly(True)
        self.test_results.setMinimumHeight(150)
        font = QFont("Consolas", 10)
        font.setStyleHint(QFont.Monospace)
        self.test_results.setFont(font)
        results_layout.addWidget(self.test_results)

        layout.addWidget(results_group)

        # 해석 가이드
        guide_group = QGroupBox("Interpretation Guide")
        guide_layout = QVBoxLayout(guide_group)
        guide_text = QLabel(
            "<b>Significance (p-value):</b><br>"
            "• p < 0.001: Highly significant ***<br>"
            "• p < 0.01: Very significant **<br>"
            "• p < 0.05: Significant *<br>"
            "• p ≥ 0.05: Not significant<br><br>"
            "<b>Effect Size (Cohen's d):</b><br>"
            "• |d| < 0.2: Negligible<br>"
            "• |d| < 0.5: Small<br>"
            "• |d| < 0.8: Medium<br>"
            "• |d| ≥ 0.8: Large<br><br>"
            "<b>Correlation Strength:</b><br>"
            "• |r| < 0.3: Weak<br>"
            "• |r| < 0.7: Moderate<br>"
            "• |r| ≥ 0.7: Strong"
        )
        guide_text.setWordWrap(True)
        self._guide_text = guide_text
        guide_layout.addWidget(guide_text)
        layout.addWidget(guide_group)

        layout.addStretch()

        self.tab_widget.addTab(tab, "Statistical Tests")

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
        self.analyze_btn.setToolTip("Analyze comparison statistics")
        self.analyze_btn.clicked.connect(self._analyze_difference)
        layout.addWidget(self.analyze_btn)

        # 차이 요약
        self.diff_summary = QLabel("")
        self.diff_summary.setWordWrap(True)
        layout.addWidget(self.diff_summary)

        # 차이 테이블
        self.diff_table = QTableWidget()
        self.diff_table.setAlternatingRowColors(True)
        self.diff_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.diff_table)

        # Export CSV button
        export_diff_btn = QPushButton("Export CSV")
        export_diff_btn.setToolTip("Export difference table to CSV")
        export_diff_btn.clicked.connect(self._export_diff_csv)
        layout.addWidget(export_diff_btn)

        # Store diff_df for export
        self._last_diff_df = None

        self.tab_widget.addTab(tab, "Difference")

    def _connect_signals(self):
        """시그널 연결 (via adapter)"""
        self._state_adapter.comparison_settings_changed.connect(self.refresh)
        self._state_adapter.dataset_added.connect(self._update_dataset_combos)
        self._state_adapter.dataset_removed.connect(self._update_dataset_combos)

        # Apply initial theme
        self._apply_theme_styles()

    # ------------------------------------------------------------------
    # Theme
    # ------------------------------------------------------------------

    def apply_theme(self, is_light: bool) -> None:
        """Apply light/dark theme colors."""
        self._is_light = is_light
        self._apply_theme_styles()

    def _apply_theme_styles(self) -> None:
        """Update all theme-dependent styles."""
        is_light = self._is_light
        tab_inactive = "#6B7280" if is_light else "#9CA3AF"
        tab_active = "#3B82F6" if is_light else "#59B8E3"

        self.tab_widget.setStyleSheet(f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                background: transparent;
                border: none;
                padding: 6px 12px;
                font-size: 11px;
                color: {tab_inactive};
            }}
            QTabBar::tab:selected {{
                color: {tab_active};
                font-weight: 600;
                border-bottom: 2px solid {tab_active};
            }}
        """)

        guide_bg = "#f8f9fa" if is_light else "#334155"
        guide_fg = "#111827" if is_light else "#E2E8F0"
        if hasattr(self, '_guide_text'):
            self._guide_text.setStyleSheet(
                f"padding: 4px; background: {guide_bg}; border-radius: 4px; color: {guide_fg};"
            )

        summary_bg = "#f8f9fa" if is_light else "#334155"
        summary_fg = "#111827" if is_light else "#E2E8F0"
        if hasattr(self, 'diff_summary'):
            self.diff_summary.setStyleSheet(
                f"padding: 8px; background: {summary_bg}; border-radius: 4px; color: {summary_fg};"
            )

        # QTextEdit for test results
        te_bg = "#FFFFFF" if is_light else "#1E293B"
        te_fg = "#111827" if is_light else "#E2E8F0"
        if hasattr(self, 'test_results'):
            self.test_results.setStyleSheet(
                f"background-color: {te_bg}; color: {te_fg};"
            )

    def refresh(self):
        """패널 새로고침"""
        self._update_column_combos()
        self._update_dataset_combos()
        self._update_test_combos()
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

        self._last_diff_df = diff_df

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

    def _run_statistical_test(self):
        """통계 검정 실행"""
        dataset_a_id = self.test_dataset_a.currentData()
        dataset_b_id = self.test_dataset_b.currentData()
        value_column = self.test_column_combo.currentText()
        test_type = self.test_type_combo.currentData()

        if not dataset_a_id or not dataset_b_id or not value_column:
            self.test_results.setHtml("<span style='color: red;'>Please select datasets and column.</span>")
            return

        if dataset_a_id == dataset_b_id:
            self.test_results.setHtml("<span style='color: red;'>Please select different datasets.</span>")
            return

        # 통계 검정 수행
        result = self.engine.perform_statistical_test(
            dataset_a_id, dataset_b_id, value_column, test_type
        )

        if not result:
            self.test_results.setHtml("<span style='color: red;'>Failed to perform statistical test.</span>")
            return

        if "error" in result and result.get("statistic") is None:
            self.test_results.setHtml(f"<span style='color: red;'>Error: {result['error']}</span>")
            return

        # 데이터셋 이름 가져오기
        meta_a = self.state.get_dataset_metadata(dataset_a_id)
        meta_b = self.state.get_dataset_metadata(dataset_b_id)
        name_a = meta_a.name if meta_a else dataset_a_id
        name_b = meta_b.name if meta_b else dataset_b_id

        # 유의성 표시
        p_value = result.get("p_value")
        if p_value is not None:
            if p_value < 0.001:
                sig_stars = "***"
                sig_color = "#d32f2f"
            elif p_value < 0.01:
                sig_stars = "**"
                sig_color = "#f57c00"
            elif p_value < 0.05:
                sig_stars = "*"
                sig_color = "#388e3c"
            else:
                sig_stars = ""
                sig_color = "#757575"
        else:
            sig_stars = ""
            sig_color = "#757575"

        # Theme-aware HTML colors
        _tbl_bg = "#f5f5f5" if self._is_light else "#334155"
        _interp_bg = "#e3f2fd" if self._is_light else "#1E3A5F"
        _heading_color = "#1976d2" if self._is_light else "#59B8E3"
        _fg = "#111827" if self._is_light else "#E2E8F0"

        # 결과 HTML 생성
        html = f"""
        <h3 style='margin: 0; color: {_heading_color};'>Statistical Test Results</h3>
        <hr>
        <table style='width: 100%; font-size: 11pt; color: {_fg};'>
            <tr><td><b>Comparison:</b></td><td>{name_a} vs {name_b}</td></tr>
            <tr><td><b>Column:</b></td><td>{value_column}</td></tr>
            <tr><td><b>Test:</b></td><td>{result.get('test_name', 'N/A')}</td></tr>
        </table>
        <br>
        <table style='width: 100%; font-size: 11pt; background: {_tbl_bg}; padding: 8px; color: {_fg};'>
            <tr>
                <td><b>Statistic:</b></td>
                <td style='text-align: right;'>{result.get('statistic', 'N/A'):.4f if result.get('statistic') else 'N/A'}</td>
            </tr>
            <tr>
                <td><b>p-value:</b></td>
                <td style='text-align: right; color: {sig_color}; font-weight: bold;'>
                    {p_value:.6f if p_value else 'N/A'} {sig_stars}
                </td>
            </tr>
            <tr>
                <td><b>Effect Size (d):</b></td>
                <td style='text-align: right;'>{result.get('effect_size', 'N/A'):.4f if result.get('effect_size') else 'N/A'}</td>
            </tr>
            <tr>
                <td><b>Significant:</b></td>
                <td style='text-align: right;'>
                    {'<span style="color: green;">Yes</span>' if result.get('is_significant') else '<span style="color: gray;">No</span>'}
                </td>
            </tr>
        </table>
        <br>
        <div style='background: {_interp_bg}; padding: 8px; border-radius: 4px; color: {_fg};'>
            <b>Interpretation:</b><br>
            {result.get('interpretation', '')}
        </div>
        """

        self.test_results.setHtml(html)

    def _run_correlation(self):
        """상관관계 분석 실행"""
        dataset_a_id = self.test_dataset_a.currentData()
        dataset_b_id = self.test_dataset_b.currentData()
        value_column = self.test_column_combo.currentText()
        method = self.corr_method_combo.currentData()

        if not dataset_a_id or not dataset_b_id or not value_column:
            self.test_results.setHtml("<span style='color: red;'>Please select datasets and column.</span>")
            return

        # 상관관계 계산
        result = self.engine.calculate_correlation(
            dataset_a_id, dataset_b_id, value_column, value_column, method
        )

        if not result:
            self.test_results.setHtml("<span style='color: red;'>Failed to calculate correlation.</span>")
            return

        if "error" in result and result.get("correlation") is None:
            self.test_results.setHtml(f"<span style='color: red;'>Error: {result['error']}</span>")
            return

        # 데이터셋 이름
        meta_a = self.state.get_dataset_metadata(dataset_a_id)
        meta_b = self.state.get_dataset_metadata(dataset_b_id)
        name_a = meta_a.name if meta_a else dataset_a_id
        name_b = meta_b.name if meta_b else dataset_b_id

        # 상관계수 색상
        corr = result.get("correlation", 0)
        if corr is not None:
            if corr > 0.5:
                corr_color = "#388e3c"  # 녹색 (강한 양의 상관)
            elif corr > 0:
                corr_color = "#7cb342"  # 연녹색
            elif corr > -0.5:
                corr_color = "#f57c00"  # 주황색
            else:
                corr_color = "#d32f2f"  # 빨간색 (강한 음의 상관)
        else:
            corr_color = "#757575"

        # 결과 HTML
        html = f"""
        <h3 style='margin: 0; color: #1976d2;'>Correlation Analysis Results</h3>
        <hr>
        <table style='width: 100%; font-size: 11pt;'>
            <tr><td><b>Comparison:</b></td><td>{name_a} vs {name_b}</td></tr>
            <tr><td><b>Column:</b></td><td>{value_column}</td></tr>
            <tr><td><b>Method:</b></td><td>{result.get('method', method.title())}</td></tr>
        </table>
        <br>
        <table style='width: 100%; font-size: 11pt; background: #f5f5f5; padding: 8px;'>
            <tr>
                <td><b>Correlation (r):</b></td>
                <td style='text-align: right; color: {corr_color}; font-weight: bold; font-size: 14pt;'>
                    {corr:.4f if corr is not None else 'N/A'}
                </td>
            </tr>
            <tr>
                <td><b>p-value:</b></td>
                <td style='text-align: right;'>{result.get('p_value', 'N/A'):.6f if result.get('p_value') else 'N/A'}</td>
            </tr>
            <tr>
                <td><b>Strength:</b></td>
                <td style='text-align: right;'>{result.get('strength', 'N/A').title() if result.get('strength') else 'N/A'}</td>
            </tr>
            <tr>
                <td><b>Significant:</b></td>
                <td style='text-align: right;'>
                    {'<span style="color: green;">Yes</span>' if result.get('is_significant') else '<span style="color: gray;">No</span>'}
                </td>
            </tr>
        </table>
        <br>
        <div style='background: #e3f2fd; padding: 8px; border-radius: 4px;'>
            <b>Interpretation:</b><br>
            {result.get('interpretation', '')}
        </div>
        """

        self.test_results.setHtml(html)

    def _update_test_combos(self, _=None):
        """통계 검정 탭의 콤보박스 업데이트"""
        dataset_ids = list(self.state.dataset_metadata.keys())

        # Test Dataset A
        current_a = self.test_dataset_a.currentData()
        self.test_dataset_a.clear()
        for did in dataset_ids:
            metadata = self.state.get_dataset_metadata(did)
            name = metadata.name if metadata else did
            self.test_dataset_a.addItem(name, did)
        if current_a in dataset_ids:
            idx = dataset_ids.index(current_a)
            self.test_dataset_a.setCurrentIndex(idx)

        # Test Dataset B
        current_b = self.test_dataset_b.currentData()
        self.test_dataset_b.clear()
        for did in dataset_ids:
            metadata = self.state.get_dataset_metadata(did)
            name = metadata.name if metadata else did
            self.test_dataset_b.addItem(name, did)
        if current_b in dataset_ids:
            idx = dataset_ids.index(current_b)
            self.test_dataset_b.setCurrentIndex(idx)
        elif len(dataset_ids) >= 2:
            self.test_dataset_b.setCurrentIndex(1)

        # Test Column Combo
        if dataset_ids:
            common_cols = self.engine.get_common_columns(dataset_ids)
            numeric_cols = []
            for col in common_cols:
                ds = self.engine.get_dataset(dataset_ids[0])
                if ds and ds.df is not None and col in ds.df.columns:
                    dtype = str(ds.df[col].dtype)
                    if dtype.startswith(('Int', 'Float', 'UInt')):
                        numeric_cols.append(col)

            current_col = self.test_column_combo.currentText()
            self.test_column_combo.clear()
            self.test_column_combo.addItems(numeric_cols)
            if current_col in numeric_cols:
                self.test_column_combo.setCurrentText(current_col)

    # ------------------------------------------------------------------
    # CSV Export
    # ------------------------------------------------------------------

    def _export_table_to_csv(self, table: QTableWidget, default_name: str = "export.csv") -> None:
        """Export a QTableWidget to CSV via file dialog."""
        import csv

        path, _ = QFileDialog.getSaveFileName(
            self, "Export CSV", default_name, "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return

        try:
            col_count = table.columnCount()
            row_count = table.rowCount()

            # Headers
            headers = []
            for c in range(col_count):
                h = table.horizontalHeaderItem(c)
                headers.append(h.text() if h else f"col_{c}")

            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(headers)
                for r in range(row_count):
                    row_data = []
                    for c in range(col_count):
                        item = table.item(r, c)
                        row_data.append(item.text() if item else "")
                    writer.writerow(row_data)
        except Exception as e:
            logger.exception("comparison_stats_panel.export_table_csv.error")
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export Error", f"Failed to export CSV:\n{e}")

    def _export_stats_csv(self) -> None:
        """Export the Statistics table to CSV."""
        if self.stats_table.rowCount() == 0:
            return
        self._export_table_to_csv(self.stats_table, "comparison_statistics.csv")

    def _export_diff_csv(self) -> None:
        """Export the Difference table to CSV."""
        if self._last_diff_df is not None:
            import csv

            path, _ = QFileDialog.getSaveFileName(
                self, "Export CSV", "comparison_difference.csv",
                "CSV Files (*.csv);;All Files (*)"
            )
            if not path:
                return
            try:
                columns = list(self._last_diff_df.columns)
                with open(path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(columns)
                    for i in range(len(self._last_diff_df)):
                        row = [self._last_diff_df[col][i] for col in columns]
                        writer.writerow(row)
            except Exception as e:
                logger.exception("comparison_stats_panel.export_diff_csv.error")
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.warning(self, "Export Error", f"Failed to export CSV:\n{e}")
        elif self.diff_table.rowCount() > 0:
            self._export_table_to_csv(self.diff_table, "comparison_difference.csv")
