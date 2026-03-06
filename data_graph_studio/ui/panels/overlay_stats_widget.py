"""
Overlay Statistics Widget - 오버레이 통계 위젯

오버레이 비교 모드에서 그래프 위에 표시되는 통계 정보 위젯
"""

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QFrame,
    QGridLayout,
    QPushButton,
    QGraphicsOpacityEffect,
)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation

from ...core.data_engine import DataEngine
from ...core.state import AppState


class DatasetLegendItem(QFrame):
    """데이터셋 범례 아이템"""

    def __init__(
        self,
        dataset_id: str,
        name: str,
        color: str,
        is_light: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.dataset_id = dataset_id

        bg = "rgba(255, 255, 255, 0.9)" if is_light else "rgba(30, 41, 59, 0.9)"
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 2px solid {color};
                border-radius: 4px;
                padding: 2px 6px;
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(6)

        # 색상 인디케이터
        color_box = QFrame()
        color_box.setFixedSize(12, 12)
        color_box.setStyleSheet(f"background: {color}; border-radius: 2px;")
        layout.addWidget(color_box)

        # 이름
        fg = "#111827" if is_light else "#E2E8F0"
        name_label = QLabel(name)
        name_label.setStyleSheet(f"font-weight: bold; font-size: 11px; color: {fg};")
        layout.addWidget(name_label)


class StatisticBadge(QFrame):
    """통계 배지 (작은 통계 정보 표시)"""

    def __init__(
        self,
        label: str,
        value: str,
        color: str = "#333",
        is_light: bool = False,
        parent=None,
    ):
        super().__init__(parent)

        bg = "rgba(255, 255, 255, 0.85)" if is_light else "rgba(30, 41, 59, 0.85)"
        border = "#ddd" if is_light else "#475569"
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 4px;
                padding: 2px 4px;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(0)

        label_fg = "#666" if is_light else "#9CA3AF"
        label_widget = QLabel(label)
        label_widget.setStyleSheet(f"font-size: 9px; color: {label_fg};")
        label_widget.setAlignment(Qt.AlignCenter)
        layout.addWidget(label_widget)

        value_widget = QLabel(value)
        value_widget.setStyleSheet(
            f"font-size: 11px; font-weight: bold; color: {color};"
        )
        value_widget.setAlignment(Qt.AlignCenter)
        layout.addWidget(value_widget)


class OverlayStatsWidget(QWidget):
    """
    오버레이 통계 위젯

    그래프 패널 위에 반투명하게 표시되며 다음 정보를 제공:
    - 비교 중인 데이터셋 범례
    - 주요 통계 비교 (mean, max, min)
    - 통계적 유의성 표시
    """

    close_requested = Signal()  # 닫기 요청
    expand_requested = Signal()  # 확장 요청 (전체 통계 패널 열기)

    def __init__(self, engine: DataEngine, state: AppState, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.state = state
        self._is_light: bool = False  # Default: dark (midnight) theme

        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        # 메인 컨테이너
        self.container = QFrame(self)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.container)

        container_layout = QVBoxLayout(self.container)
        container_layout.setContentsMargins(8, 6, 8, 6)
        container_layout.setSpacing(6)

        # 헤더 (타이틀 + 버튼)
        header_layout = QHBoxLayout()

        self._title_label = QLabel("Comparison Stats")
        header_layout.addWidget(self._title_label)

        header_layout.addStretch()

        # 확장 버튼
        expand_btn = QPushButton("⊕")
        expand_btn.setFixedSize(20, 20)
        expand_btn.setToolTip("Show full statistics panel")
        expand_btn.clicked.connect(self.expand_requested.emit)
        expand_btn.setStyleSheet("border: none; font-size: 14px;")
        header_layout.addWidget(expand_btn)

        # 닫기 버튼
        close_btn = QPushButton("×")
        close_btn.setFixedSize(20, 20)
        close_btn.setToolTip("Close statistics overlay")
        close_btn.clicked.connect(self.close_requested.emit)
        close_btn.setStyleSheet("border: none; font-size: 14px;")
        header_layout.addWidget(close_btn)

        container_layout.addLayout(header_layout)

        # 범례 영역
        self.legend_layout = QHBoxLayout()
        self.legend_layout.setSpacing(4)
        container_layout.addLayout(self.legend_layout)

        # 통계 그리드
        self.stats_grid = QGridLayout()
        self.stats_grid.setSpacing(4)
        container_layout.addLayout(self.stats_grid)

        # 유의성 표시
        self.significance_label = QLabel("")
        self.significance_label.setAlignment(Qt.AlignCenter)
        self.significance_label.setStyleSheet("font-size: 10px; padding: 4px;")
        container_layout.addWidget(self.significance_label)

        # 크기 설정
        self.setMinimumWidth(200)
        self.setMaximumWidth(400)

        # Apply initial theme
        self._apply_container_theme()

    def apply_theme(self, is_light: bool) -> None:
        """Apply light/dark theme colors."""
        self._is_light = is_light
        self._apply_container_theme()

    def _apply_container_theme(self) -> None:
        """Update container and title styling based on _is_light."""
        is_light = self._is_light
        bg = "rgba(255, 255, 255, 0.95)" if is_light else "rgba(30, 41, 59, 0.95)"
        border = "#ccc" if is_light else "#475569"
        self.container.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border: 1px solid {border};
                border-radius: 8px;
            }}
        """)
        title_fg = "#333" if is_light else "#E2E8F0"
        if hasattr(self, "_title_label"):
            self._title_label.setStyleSheet(
                f"font-weight: bold; font-size: 12px; color: {title_fg};"
            )

    def _connect_signals(self):
        self.state.comparison_settings_changed.connect(self.refresh)
        self.state.dataset_added.connect(self.refresh)
        self.state.dataset_removed.connect(self.refresh)

    def refresh(self):
        """통계 정보 새로고침"""
        # 범례 클리어
        while self.legend_layout.count() > 0:
            item = self.legend_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 통계 그리드 클리어
        while self.stats_grid.count() > 0:
            item = self.stats_grid.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        # 비교 데이터셋 가져오기
        dataset_ids = self.state.comparison_dataset_ids
        if not dataset_ids:
            self.significance_label.setText("No datasets selected for comparison")
            return

        # 범례 추가
        for did in dataset_ids[:4]:  # 최대 4개
            metadata = self.state.get_dataset_metadata(did)
            if metadata:
                legend_item = DatasetLegendItem(
                    did, metadata.name, metadata.color, self._is_light
                )
                self.legend_layout.addWidget(legend_item)

        self.legend_layout.addStretch()

        # 공통 숫자 컬럼 찾기
        common_cols = self.engine.get_common_columns(dataset_ids)
        numeric_cols = []
        for col in common_cols:
            ds = self.engine.get_dataset(dataset_ids[0])
            if ds and ds.df is not None and col in ds.df.columns:
                dtype = str(ds.df[col].dtype)
                if dtype.startswith(("Int", "Float", "UInt")):
                    numeric_cols.append(col)

        if not numeric_cols:
            self.significance_label.setText("No common numeric columns")
            return

        # 첫 번째 숫자 컬럼의 통계
        value_col = numeric_cols[0]

        # 통계 계산
        stats = self.engine.get_comparison_statistics(dataset_ids, value_col)

        if not stats:
            return

        # 헤더 행
        self.stats_grid.addWidget(QLabel(""), 0, 0)
        for col, did in enumerate(dataset_ids[:4], 1):
            metadata = self.state.get_dataset_metadata(did)
            name = metadata.name[:10] if metadata else did[:10]
            header = QLabel(name)
            header.setStyleSheet("font-size: 9px; font-weight: bold;")
            header.setAlignment(Qt.AlignCenter)
            self.stats_grid.addWidget(header, 0, col)

        # 통계 행
        stat_names = [("Mean", "mean"), ("Max", "max"), ("Min", "min")]
        for row, (display_name, stat_key) in enumerate(stat_names, 1):
            label_fg = "#666" if self._is_light else "#9CA3AF"
            label = QLabel(display_name)
            label.setStyleSheet(f"font-size: 10px; color: {label_fg};")
            self.stats_grid.addWidget(label, row, 0)

            values = []
            for col, did in enumerate(dataset_ids[:4], 1):
                if did in stats:
                    value = stats[did].get(stat_key)
                    if value is not None:
                        text = f"{value:,.1f}"
                        values.append(value)
                    else:
                        text = "-"
                else:
                    text = "-"

                value_label = QLabel(text)
                value_label.setStyleSheet("font-size: 10px;")
                value_label.setAlignment(Qt.AlignCenter)
                self.stats_grid.addWidget(value_label, row, col)

            # 최대값 하이라이트
            if len(values) >= 2:
                max_val = max(values)
                for col, did in enumerate(dataset_ids[:4], 1):
                    if did in stats:
                        v = stats[did].get(stat_key)
                        if v == max_val:
                            widget = self.stats_grid.itemAtPosition(row, col).widget()
                            widget.setStyleSheet(
                                "font-size: 10px; font-weight: bold; color: #2e7d32;"
                            )

        # 통계적 유의성 검정 (두 데이터셋일 때만)
        if len(dataset_ids) == 2:
            test_result = self.engine.perform_statistical_test(
                dataset_ids[0], dataset_ids[1], value_col, "auto"
            )
            if test_result and "error" not in test_result:
                p_value = test_result.get("p_value")
                if p_value is not None:
                    if p_value < 0.001:
                        sig_text = "Highly Significant (p < 0.001) ***"
                        sig_color = "#d32f2f"
                    elif p_value < 0.01:
                        sig_text = "Very Significant (p < 0.01) **"
                        sig_color = "#f57c00"
                    elif p_value < 0.05:
                        sig_text = "Significant (p < 0.05) *"
                        sig_color = "#388e3c"
                    else:
                        sig_text = "Not Significant (p ≥ 0.05)"
                        sig_color = "#757575"

                    self.significance_label.setText(sig_text)
                    self.significance_label.setStyleSheet(
                        f"font-size: 10px; padding: 4px; background: rgba({int(sig_color[1:3], 16)}, {int(sig_color[3:5], 16)}, {int(sig_color[5:7], 16)}, 0.1); border-radius: 4px; color: {sig_color};"
                    )
        else:
            muted = "#666" if self._is_light else "#9CA3AF"
            self.significance_label.setText(f"Comparing {len(dataset_ids)} datasets")
            self.significance_label.setStyleSheet(
                f"font-size: 10px; padding: 4px; color: {muted};"
            )

    def set_position(self, position: str = "top-right"):
        """위젯 위치 설정"""
        parent = self.parent()
        if not parent:
            return

        margin = 10
        if position == "top-right":
            x = parent.width() - self.width() - margin
            y = margin
        elif position == "top-left":
            x = margin
            y = margin
        elif position == "bottom-right":
            x = parent.width() - self.width() - margin
            y = parent.height() - self.height() - margin
        elif position == "bottom-left":
            x = margin
            y = parent.height() - self.height() - margin
        else:
            x = margin
            y = margin

        self.move(x, y)

    @staticmethod
    def _reduce_animations() -> bool:
        """Check if animations should be reduced (Item 13)"""
        from PySide6.QtCore import QSettings

        settings = QSettings("DataGraphStudio", "DGS")
        return settings.value("accessibility/reduce_animations", False, type=bool)

    def show_animated(self):
        """애니메이션과 함께 표시"""
        self.show()
        self.refresh()

        if self._reduce_animations():
            return

        # 페이드인 효과
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)

        self.animation = QPropertyAnimation(effect, b"opacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.start()

    def hide_animated(self):
        """애니메이션과 함께 숨기기"""
        if self._reduce_animations():
            self.hide()
            return

        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)

        self.animation = QPropertyAnimation(effect, b"opacity")
        self.animation.setDuration(200)
        self.animation.setStartValue(1)
        self.animation.setEndValue(0)
        self.animation.finished.connect(self.hide)
        self.animation.start()
