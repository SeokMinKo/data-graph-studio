"""
Summary Panel - Modern Statistics Cards with Micro-animations
"""

from typing import Dict, Any, Optional

from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame,
    QScrollArea, QSizePolicy, QGraphicsDropShadowEffect
)
from PySide6.QtCore import Qt, Slot, QPropertyAnimation, QEasingCurve, Property
from PySide6.QtGui import QFont, QColor

from ...core.state import AppState


class AnimatedNumber(QLabel):
    """Animated number label with smooth transitions"""
    
    def __init__(self, initial_value: float = 0):
        super().__init__()
        self._value = initial_value
        self._display_value = initial_value
        self._suffix = ""
        self._prefix = ""
        self._decimals = 0
        
        self.animation = QPropertyAnimation(self, b"display_value")
        self.animation.setDuration(400)
        self.animation.setEasingCurve(QEasingCurve.OutCubic)
        
        self._update_text()
    
    def get_display_value(self) -> float:
        return self._display_value
    
    def set_display_value(self, value: float):
        self._display_value = value
        self._update_text()
    
    display_value = Property(float, get_display_value, set_display_value)
    
    def set_value(self, value: float, suffix: str = "", prefix: str = "", decimals: int = 0):
        self._suffix = suffix
        self._prefix = prefix
        self._decimals = decimals
        
        self.animation.setStartValue(self._display_value)
        self.animation.setEndValue(value)
        self.animation.start()
        
        self._value = value
    
    def _update_text(self):
        if self._decimals > 0:
            formatted = f"{self._display_value:,.{self._decimals}f}"
        else:
            formatted = f"{int(self._display_value):,}"
        self.setText(f"{self._prefix}{formatted}{self._suffix}")


class StatCard(QFrame):
    """Modern stat card with glassmorphism effect"""
    
    def __init__(self, icon: str, title: str, value: str = "-", subtitle: str = "", color: str = "#6366F1"):
        super().__init__()
        self.color = color
        
        self.setObjectName("StatCard")
        self.setMinimumWidth(140)
        self.setMaximumWidth(200)
        
        # Shadow effect
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 25))
        self.setGraphicsEffect(shadow)
        
        self._setup_style()
        self._setup_ui(icon, title, value, subtitle)
    
    def _setup_style(self):
        self.setStyleSheet(f"""
            #StatCard {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 0.9),
                    stop:1 rgba(249, 250, 251, 0.95));
                border: 1px solid rgba(255, 255, 255, 0.5);
                border-radius: 16px;
            }}
            #StatCard:hover {{
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(255, 255, 255, 1),
                    stop:1 rgba(249, 250, 251, 1));
                border: 1px solid {self.color}40;
            }}
        """)
    
    def _setup_ui(self, icon: str, title: str, value: str, subtitle: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        
        # Header row with icon
        header = QHBoxLayout()
        header.setSpacing(8)
        
        # Icon badge
        icon_label = QLabel(icon)
        icon_label.setStyleSheet(f"""
            background-color: {self.color}15;
            color: {self.color};
            border-radius: 8px;
            padding: 6px;
            font-size: 16px;
        """)
        icon_label.setFixedSize(32, 32)
        icon_label.setAlignment(Qt.AlignCenter)
        header.addWidget(icon_label)
        
        # Title
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet("""
            color: #6B7280;
            font-size: 11px;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            background: transparent;
            border: none;
        """)
        header.addWidget(self.title_label, 1)
        layout.addLayout(header)
        
        # Value (large)
        self.value_label = QLabel(value)
        self.value_label.setStyleSheet(f"""
            color: #111827;
            font-size: 28px;
            font-weight: 700;
            background: transparent;
            border: none;
            margin-top: 4px;
        """)
        layout.addWidget(self.value_label)
        
        # Subtitle with trend indicator
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setStyleSheet("""
                color: #9CA3AF;
                font-size: 11px;
                background: transparent;
                border: none;
            """)
            layout.addWidget(self.subtitle_label)
        else:
            self.subtitle_label = None
    
    def set_value(self, value: str, subtitle: str = ""):
        self.value_label.setText(value)
        if self.subtitle_label:
            self.subtitle_label.setText(subtitle)
    
    def set_trend(self, trend: float, suffix: str = "%"):
        """Set trend indicator (positive/negative)"""
        if self.subtitle_label:
            if trend > 0:
                self.subtitle_label.setText(f"↑ +{trend:.1f}{suffix}")
                self.subtitle_label.setStyleSheet("""
                    color: #10B981;
                    font-size: 11px;
                    font-weight: 500;
                    background: transparent;
                    border: none;
                """)
            elif trend < 0:
                self.subtitle_label.setText(f"↓ {trend:.1f}{suffix}")
                self.subtitle_label.setStyleSheet("""
                    color: #EF4444;
                    font-size: 11px;
                    font-weight: 500;
                    background: transparent;
                    border: none;
                """)
            else:
                self.subtitle_label.setText("→ 0%")
                self.subtitle_label.setStyleSheet("""
                    color: #9CA3AF;
                    font-size: 11px;
                    background: transparent;
                    border: none;
                """)


class MiniSparkline(QFrame):
    """Mini sparkline chart for trends"""
    
    def __init__(self, data: list = None, color: str = "#6366F1"):
        super().__init__()
        self.data = data or []
        self.color = color
        self.setFixedHeight(32)
        self.setMinimumWidth(60)
        
    # TODO: Implement paintEvent for actual sparkline


class SummaryPanel(QWidget):
    """
    Modern Summary Panel with animated stat cards
    
    Features:
    - Glassmorphism cards
    - Animated number transitions
    - Trend indicators
    - Mini sparklines
    - Responsive layout
    """
    
    def __init__(self, state: AppState):
        super().__init__()
        self.state = state
        
        self._setup_ui()
        self._connect_signals()
    
    def _setup_ui(self):
        """Setup modern UI"""
        self.setMinimumHeight(140)
        self.setMaximumHeight(220)
        
        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(16, 12, 16, 12)
        main_layout.setSpacing(12)
        
        # Header with title and context
        header = QHBoxLayout()
        header.setSpacing(12)
        
        # Title with icon
        title_container = QHBoxLayout()
        title_container.setSpacing(8)
        
        title_icon = QLabel("📊")
        title_icon.setStyleSheet("font-size: 18px; background: transparent;")
        title_container.addWidget(title_icon)
        
        title = QLabel("Overview")
        title.setStyleSheet("""
            font-weight: 600;
            font-size: 15px;
            color: #111827;
            background: transparent;
        """)
        title_container.addWidget(title)
        header.addLayout(title_container)
        
        # Context label (shows grouping/filter info)
        self.context_label = QLabel("")
        self.context_label.setStyleSheet("""
            color: #6B7280;
            font-size: 12px;
            background: transparent;
            padding: 4px 12px;
            border-radius: 12px;
        """)
        header.addWidget(self.context_label, 1)
        
        # Quick actions (optional)
        header.addStretch()
        
        main_layout.addLayout(header)
        
        # Cards scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")
        scroll.setMaximumHeight(140)
        
        # Card container with smooth scrolling
        self.card_container = QWidget()
        self.card_container.setStyleSheet("background: transparent;")
        self.card_layout = QHBoxLayout(self.card_container)
        self.card_layout.setContentsMargins(0, 4, 0, 4)
        self.card_layout.setSpacing(12)
        
        # Default stat cards with icons and colors
        self.cards = {}
        self._add_card("rows", "📋", "Total Rows", "-", color="#6366F1")
        self._add_card("columns", "⊞", "Columns", "-", color="#8B5CF6")
        self._add_card("numeric", "🔢", "Numeric", "-", color="#10B981")
        self._add_card("text", "📝", "Text/Category", "-", color="#EC4899")
        self._add_card("missing", "⚠", "Missing %", "-", color="#F59E0B")
        self._add_card("memory", "💾", "Memory", "-", color="#3B82F6")
        
        self.card_layout.addStretch()
        
        scroll.setWidget(self.card_container)
        main_layout.addWidget(scroll)
    
    def _add_card(self, key: str, icon: str, title: str, value: str = "-", color: str = "#6366F1") -> StatCard:
        """Add a stat card"""
        card = StatCard(icon, title, value, "", color)
        self.cards[key] = card
        self.card_layout.addWidget(card)
        return card
    
    def _connect_signals(self):
        """Connect state signals"""
        self.state.summary_updated.connect(self._on_summary_updated)
        self.state.selection_changed.connect(self._on_selection_changed)
        self.state.group_zone_changed.connect(self._on_group_changed)
        self.state.value_zone_changed.connect(self._on_value_changed)
    
    @Slot(dict)
    def _on_summary_updated(self, stats: Dict[str, Any]):
        """Update summary with new stats"""
        # Basic stats
        if 'total_rows' in stats:
            self.cards['rows'].set_value(f"{stats['total_rows']:,}")

        if 'total_columns' in stats:
            self.cards['columns'].set_value(f"{stats['total_columns']}")

        # Numeric columns count
        if 'numeric_columns' in stats:
            self.cards['numeric'].set_value(f"{stats['numeric_columns']}")

        # Text/Category columns count
        if 'text_columns' in stats:
            self.cards['text'].set_value(f"{stats['text_columns']}")

        # Missing data percentage
        if 'missing_percent' in stats:
            pct = stats['missing_percent']
            if pct == 0:
                self.cards['missing'].set_value("0%", "Clean!")
            elif pct < 5:
                self.cards['missing'].set_value(f"{pct:.1f}%", "Low")
            else:
                self.cards['missing'].set_value(f"{pct:.1f}%", "High")

        if 'memory_mb' in stats:
            mb = stats['memory_mb']
            if mb >= 1024:
                self.cards['memory'].set_value(f"{mb/1024:.1f}", "GB")
            elif mb >= 1:
                self.cards['memory'].set_value(f"{mb:.1f}", "MB")
            else:
                self.cards['memory'].set_value(f"{mb*1024:.0f}", "KB")

        # Dynamic value cards
        self._update_value_cards(stats)
    
    @Slot()
    def _on_selection_changed(self):
        """Handle selection change"""
        if self.state.selection.has_selection:
            count = self.state.selection.selection_count
            total = self.state.total_rows
            pct = (count / total * 100) if total > 0 else 0

            self.context_label.setText(f"Selected: {count:,} of {total:,} rows ({pct:.1f}%)")
            self.context_label.setStyleSheet("""
                color: #10B981;
                font-size: 12px;
                background: #10B98115;
                padding: 4px 12px;
                border-radius: 12px;
            """)
        else:
            self.context_label.setText("")
            self.context_label.setStyleSheet("""
                color: #6B7280;
                font-size: 12px;
                background: transparent;
                padding: 4px 12px;
                border-radius: 12px;
            """)
    
    @Slot()
    def _on_group_changed(self):
        """Handle group change"""
        groups = self.state.group_columns
        if groups:
            group_names = ", ".join(g.name for g in groups[:3])
            if len(groups) > 3:
                group_names += f" +{len(groups) - 3}"
            
            self.context_label.setText(f"Grouped by: {group_names}")
            self.context_label.setStyleSheet("""
                color: #6366F1;
                font-size: 12px;
                background: #6366F115;
                padding: 4px 12px;
                border-radius: 12px;
            """)
    
    @Slot()
    def _on_value_changed(self):
        """Handle value zone change"""
        pass
    
    def _update_value_cards(self, stats: Dict[str, Any]):
        """Update dynamic value-based cards"""
        # Remove old dynamic cards
        for key in list(self.cards.keys()):
            if key.startswith("value_"):
                card = self.cards.pop(key)
                self.card_layout.removeWidget(card)
                card.deleteLater()
        
        # Add new value cards
        colors = ["#EC4899", "#3B82F6", "#14B8A6", "#F97316", "#8B5CF6"]
        
        for i, value_col in enumerate(self.state.value_columns):
            name = value_col.name
            agg = value_col.aggregation.value.upper()
            
            if name in stats and isinstance(stats[name], dict):
                col_stats = stats[name]
                color = colors[i % len(colors)]
                
                # Create card
                card = StatCard(
                    "📈",
                    f"{name[:12]}{'...' if len(name) > 12 else ''}",
                    self._format_value(col_stats.get('mean', col_stats.get('sum', '-'))),
                    f"Min: {self._format_value(col_stats.get('min', '-'))} → Max: {self._format_value(col_stats.get('max', '-'))}",
                    color
                )
                
                key = f"value_{name}"
                self.cards[key] = card
                self.card_layout.insertWidget(self.card_layout.count() - 1, card)
    
    def _format_value(self, value) -> str:
        """Format value with smart number formatting"""
        if value is None or value == '-':
            return "-"
        
        if isinstance(value, (int, float)):
            if abs(value) >= 1_000_000_000:
                return f"{value/1_000_000_000:.1f}B"
            elif abs(value) >= 1_000_000:
                return f"{value/1_000_000:.1f}M"
            elif abs(value) >= 1_000:
                return f"{value/1_000:.1f}K"
            elif isinstance(value, float):
                return f"{value:.2f}"
            else:
                return f"{value:,}"
        
        return str(value)
    
    def refresh(self):
        """Refresh panel"""
        self._on_selection_changed()
        self._on_group_changed()
    
    def clear(self):
        """Clear all cards"""
        for card in self.cards.values():
            card.set_value("-")
        self.context_label.setText("")
