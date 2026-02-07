"""
LegendSettingsPanel - Compact Legend Settings Panel
"""

from typing import List, Dict, Any

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QComboBox, QCheckBox, QScrollArea, QGroupBox, QPushButton,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

from ..floatable import FloatButton
from .graph_widgets import ColorButton
from ...core.state import AppState




# ==================== Legend Panel ====================

class LegendSettingsPanel(QFrame):
    """Compact Legend Settings Panel"""
    
    settings_changed = Signal()
    
    DEFAULT_COLORS = [
        "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd",
        "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"
    ]
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        self.setObjectName("LegendPanel")
        self.setMinimumWidth(160)
        self.setMaximumWidth(200)
        
        self._series_items: List[Dict] = []
        self._setup_ui()
        self._apply_style()
    
    def _apply_style(self):
        # Styles now handled by global theme stylesheet
        pass
    
    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(8)

        # Header with float button
        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)

        header = QLabel("📊 Legend")
        header.setObjectName("sectionHeader")
        header_layout.addWidget(header)

        header_layout.addStretch()

        self.float_btn = FloatButton()
        header_layout.addWidget(self.float_btn)

        layout.addLayout(header_layout)

        # Legend Options
        options_group = QGroupBox("Options")
        options_layout = QVBoxLayout(options_group)
        
        self.show_legend_check = QCheckBox("Show Legend")
        self.show_legend_check.setChecked(True)
        self.show_legend_check.stateChanged.connect(self._on_settings_changed)
        options_layout.addWidget(self.show_legend_check)
        
        pos_layout = QHBoxLayout()
        pos_layout.addWidget(QLabel("Position:"))
        self.legend_pos_combo = QComboBox()
        self.legend_pos_combo.addItems([
            "Top Right", "Top Left", "Bottom Right", "Bottom Left",
            "Top Center", "Bottom Center", "Right", "Left"
        ])
        self.legend_pos_combo.currentIndexChanged.connect(self._on_settings_changed)
        pos_layout.addWidget(self.legend_pos_combo)
        options_layout.addLayout(pos_layout)
        
        layout.addWidget(options_group)
        
        # Series List
        series_group = QGroupBox("Series")
        series_layout = QVBoxLayout(series_group)
        
        # Scroll area for series list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setMinimumHeight(150)
        
        self.series_container = QWidget()
        self.series_list_layout = QVBoxLayout(self.series_container)
        self.series_list_layout.setContentsMargins(0, 0, 0, 0)
        self.series_list_layout.setSpacing(4)
        self.series_list_layout.addStretch()
        
        scroll.setWidget(self.series_container)
        series_layout.addWidget(scroll)
        
        # Buttons
        btn_layout = QHBoxLayout()
        
        show_all_btn = QPushButton("Show All")
        show_all_btn.setObjectName("smallButton")
        show_all_btn.clicked.connect(self._show_all_series)
        btn_layout.addWidget(show_all_btn)
        
        hide_all_btn = QPushButton("Hide All")
        hide_all_btn.setObjectName("smallButton")
        hide_all_btn.clicked.connect(self._hide_all_series)
        btn_layout.addWidget(hide_all_btn)
        
        series_layout.addLayout(btn_layout)
        
        layout.addWidget(series_group)
        
        layout.addStretch()
    
    def set_series(self, series_names: List[str]):
        """시리즈 목록 설정"""
        # Clear existing
        for item in self._series_items:
            item['widget'].deleteLater()
        self._series_items.clear()
        
        # Add new series
        for i, name in enumerate(series_names):
            color = QColor(self.DEFAULT_COLORS[i % len(self.DEFAULT_COLORS)])
            self._add_series_item(name, color, i)
    
    def _add_series_item(self, name: str, color: QColor, index: int):
        """시리즈 아이템 추가"""
        item_widget = QWidget()
        item_layout = QHBoxLayout(item_widget)
        item_layout.setContentsMargins(4, 2, 4, 2)
        item_layout.setSpacing(6)
        
        # Visibility checkbox
        visible_check = QCheckBox()
        visible_check.setChecked(True)
        visible_check.stateChanged.connect(self._on_settings_changed)
        item_layout.addWidget(visible_check)
        
        # Color button
        color_btn = ColorButton(color)
        color_btn.color_changed.connect(self._on_settings_changed)
        item_layout.addWidget(color_btn)
        
        # Name label
        name_label = QLabel(name)
        name_label.setObjectName("seriesNameLabel")
        item_layout.addWidget(name_label, 1)
        
        # Insert before stretch
        self.series_list_layout.insertWidget(len(self._series_items), item_widget)
        
        self._series_items.append({
            'name': name,
            'widget': item_widget,
            'visible_check': visible_check,
            'color_btn': color_btn,
            'index': index
        })
    
    def _show_all_series(self):
        for item in self._series_items:
            item['visible_check'].setChecked(True)
    
    def _hide_all_series(self):
        for item in self._series_items:
            item['visible_check'].setChecked(False)
    
    def _on_settings_changed(self):
        self.settings_changed.emit()
    
    def get_legend_settings(self) -> Dict[str, Any]:
        """범례 설정 반환"""
        position_map = {
            0: (1, 1),   # Top Right
            1: (1, 0),   # Top Left
            2: (0, 1),   # Bottom Right
            3: (0, 0),   # Bottom Left
            4: (1, 0.5), # Top Center
            5: (0, 0.5), # Bottom Center
            6: (0.5, 1), # Right
            7: (0.5, 0), # Left
        }
        
        series_settings = []
        for item in self._series_items:
            series_settings.append({
                'name': item['name'],
                'visible': item['visible_check'].isChecked(),
                'color': item['color_btn'].color().name(),
            })
        
        return {
            'show': self.show_legend_check.isChecked(),
            'position': position_map.get(self.legend_pos_combo.currentIndex(), (1, 1)),
            'series': series_settings
        }


# ==================== Stat Panel ====================

