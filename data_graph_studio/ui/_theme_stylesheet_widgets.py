"""Standard Qt widget stylesheet — part of the theme system.

Contains CSS for built-in Qt widget classes (QWidget, QPushButton, etc.).
Extracted from _theme_base_stylesheet.py.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .theme import Theme


def widget_stylesheet(t: "Theme") -> str:
    """Return CSS for standard Qt widgets.

    Args:
        t: Current Theme instance for color token access.

    Returns:
        QSS string covering Qt built-in widget styles.
    """
    return f"""
            /* ============ Global Reset ============ */
            * {{
                font-family: 'Helvetica Neue', 'Arial';
                font-size: 13px;
            }}
            
            /* ============ Main Window ============ */
            QMainWindow {{
                background: {t.background};
            }}
            
            QWidget {{
                background-color: transparent;
                color: {t.foreground};
            }}
            
            /* ============ Cards & Surfaces ============ */
            QFrame {{
                background-color: {t.surface};
                border: {"1px solid #E5E7EB" if t.is_light() else "none"};
                border-radius: 8px;
            }}
            
            QFrame[frameShape="4"] {{  /* StyledPanel */
                background-color: {t.surface};
                border: {"1px solid #D1D5DB" if t.is_light() else "none"};
                border-radius: 8px;
                padding: 4px;
            }}
            
            /* ============ Labels ============ */
            QLabel {{
                color: {t.foreground};
                background: transparent;
                border: none;
                padding: 2px;
            }}
            
            QLabel[class="title"] {{
                font-size: 16px;
                font-weight: 600;
                color: {t.foreground};
            }}
            
            QLabel[class="subtitle"] {{
                font-size: 12px;
                color: {t.text_secondary};
            }}
            
            QLabel[class="stat-value"] {{
                font-size: 24px;
                font-weight: 700;
                color: {t.primary};
            }}
            
            /* ============ Modern Buttons ============ */
            QPushButton {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 16px;
                font-weight: 500;
                min-height: 20px;
            }}
            
            QPushButton:hover {{
                background-color: {t.surface_hover};
                border-color: {t.primary};
            }}
            
            QPushButton:pressed {{
                background-color: {t.surface_active};
            }}
            
            QPushButton:focus {{
                border: 2px solid {t.primary};
                outline: none;
            }}
            
            QPushButton[class="primary"] {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                color: white;
                border: none;
                font-weight: 600;
            }}
            
            QPushButton[class="primary"]:hover {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.accent}, stop:1 {t.primary});
            }}
            
            QPushButton[class="danger"] {{
                background-color: {t.error};
                color: white;
                border: none;
            }}
            
            QPushButton[class="icon"] {{
                background-color: transparent;
                border: none;
                padding: 6px;
                border-radius: 6px;
            }}
            
            QPushButton[class="icon"]:hover {{
                background-color: {t.hover};
            }}
            
            /* ============ Input Fields ============ */
            QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                selection-background-color: {t.primary};
                selection-color: white;
                placeholder-text-color: {t.text_secondary};
            }}
            
            QLineEdit:hover, QTextEdit:hover {{
                border-color: {t.text_secondary};
            }}
            
            QLineEdit:focus, QTextEdit:focus {{
                border: 2px solid {t.primary};
                background-color: {t.surface};
            }}
            
            QLineEdit[class="search"] {{
                border-radius: 20px;
                padding-left: 16px;
            }}
            
            /* ============ Combo Box ============ */
            QComboBox {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 12px;
                min-height: 20px;
                placeholder-text-color: {t.text_secondary};
            }}
            
            QComboBox:hover {{
                border-color: {t.primary};
            }}
            
            QComboBox::drop-down {{
                border: none;
                width: 24px;
            }}
            
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 6px solid {t.text_secondary};
                margin-right: 8px;
            }}
            
            QComboBox QAbstractItemView {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
                selection-background-color: {t.primary};
                selection-color: white;
            }}
            
            /* ============ Modern Table ============ */
            QTableView {{
                background-color: {t.surface};
                color: {t.foreground};
                border: none;
                border-radius: 8px;
                gridline-color: {t.border_light};
                selection-background-color: {t.selected};
                alternate-background-color: {t.surface_hover};
            }}
            
            QTableView::item {{
                padding: 6px 10px;
                border: none;
            }}
            
            QTableView::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            QTableView::item:hover {{
                background-color: {t.hover};
            }}
            
            QHeaderView::section {{
                background-color: {t.surface};
                color: {t.text_secondary};
                border: none;
                border-bottom: 1px solid {t.border_light};
                padding: 8px 10px;
                font-weight: 600;
                font-size: 11px;
            }}
            
            QHeaderView::section:hover {{
                background-color: {t.surface_hover};
                color: {t.foreground};
            }}
            
            /* ============ Scroll Bars ============ */
            QScrollBar:vertical {{
                background-color: transparent;
                width: 10px;
                margin: 4px;
            }}
            
            QScrollBar::handle:vertical {{
                background-color: {t.text_muted};
                border-radius: 5px;
                min-height: 30px;
            }}
            
            QScrollBar::handle:vertical:hover {{
                background-color: {t.primary};
            }}
            
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                height: 0px;
            }}
            
            QScrollBar:horizontal {{
                background-color: transparent;
                height: 10px;
                margin: 4px;
            }}
            
            QScrollBar::handle:horizontal {{
                background-color: {t.text_muted};
                border-radius: 5px;
                min-width: 30px;
            }}
            
            QScrollBar::handle:horizontal:hover {{
                background-color: {t.primary};
            }}
            
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
                width: 0px;
            }}
            
            /* ============ Splitter ============ */
            QSplitter::handle {{
                background-color: transparent;
            }}
            
            QSplitter::handle:hover {{
                background-color: {t.primary}80;
            }}
            
            QSplitter::handle:vertical {{
                height: 6px;
            }}
            
            QSplitter::handle:horizontal {{
                width: 6px;
            }}
            
            /* ============ Menu Bar ============ */
            QMenuBar {{
                background-color: {t.surface};
                color: {t.foreground};
                border-bottom: 1px solid {t.border};
                padding: 4px 8px;
            }}
            
            QMenuBar::item {{
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px;
            }}
            
            QMenuBar::item:selected {{
                background-color: {t.hover};
            }}
            
            QMenu {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 8px 4px;
            }}
            
            QMenu::item {{
                padding: 10px 24px 10px 16px;
                border-radius: 6px;
                margin: 2px 4px;
            }}
            
            QMenu::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            QMenu::separator {{
                height: 1px;
                background-color: {t.border};
                margin: 8px 12px;
            }}
            
            /* ============ Tool Bar ============ */
            QToolBar {{
                background-color: {t.surface};
                border: none;
                border-bottom: 1px solid {t.border};
                padding: 8px 16px;
                spacing: 8px;
            }}
            
            QToolBar::separator {{
                width: 1px;
                background-color: {t.border};
                margin: 4px 8px;
            }}
            
            QToolButton {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                padding: 8px 12px;
                font-size: 14px;
            }}
            
            QToolButton:hover {{
                background-color: {t.hover};
            }}
            
            QToolButton:checked {{
                background-color: {t.selected};
                color: {t.primary};
            }}
            
            /* ============ Status Bar ============ */
            QStatusBar {{
                background-color: {t.surface};
                color: {t.text_secondary};
                border-top: 1px solid {t.border};
                padding: 8px 16px;
                font-size: 12px;
            }}
            
            /* ============ Group Box ============ */
            QGroupBox {{
                background-color: transparent;
                border: none;
                border-radius: 8px;
                margin-top: 12px;
                padding: 8px;
                font-weight: 500;
            }}
            
            QGroupBox::title {{
                color: {t.text_secondary};
                subcontrol-origin: margin;
                left: 8px;
                padding: 0 4px;
                font-size: 11px;
                font-weight: 600;
            }}
            
            /* ============ Check Box ============ */
            QCheckBox {{
                spacing: 8px;
                color: {t.foreground};
            }}
            
            QCheckBox:checked {{
                color: {t.foreground};
                font-weight: 600;
            }}
            
            QCheckBox:unchecked {{
                color: {t.text_muted};
            }}
            
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border: 2px solid {t.border};
                border-radius: 4px;
                background-color: {t.surface};
            }}
            
            QCheckBox::indicator:hover {{
                border-color: {t.primary};
            }}
            
            QCheckBox::indicator:checked {{
                background-color: {t.primary};
                border-color: {t.primary};
            }}
            
            /* ============ List Widget ============ */
            QListWidget {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                padding: 4px;
            }}
            
            QListWidget::item {{
                padding: 8px 12px;
                border-radius: 6px;
                margin: 2px;
            }}
            
            QListWidget::item:hover {{
                background-color: {t.hover};
            }}
            
            QListWidget::item:selected {{
                background-color: {t.primary};
                color: white;
            }}
            
            /* ============ Tab Widget ============ */
            QTabWidget::pane {{
                background-color: {t.surface};
                border: 1px solid {t.border};
                border-radius: 8px;
                margin-top: -1px;
            }}
            
            QTabBar::tab {{
                background-color: transparent;
                color: {t.text_secondary};
                padding: 10px 20px;
                margin-right: 4px;
                border-bottom: 2px solid transparent;
            }}
            
            QTabBar::tab:hover {{
                color: {t.foreground};
            }}
            
            QTabBar::tab:selected {{
                color: {t.primary};
                border-bottom: 2px solid {t.primary};
            }}
            
            /* ============ Wizard ============ */
            QWizard {{
                background-color: {t.background};
            }}
            
            QWizard > QWidget {{
                background-color: {t.background};
            }}
            
            QWizard QLabel#qt_wizard_title {{
                background-color: {"#F3F4F6" if t.is_light() else t.surface};
                color: {t.foreground};
                font-size: 16px;
                font-weight: 600;
                padding: 16px 24px;
                border-bottom: {"1px solid #E5E7EB" if t.is_light() else f"1px solid {t.border}"};
            }}
            
            QWizard QLabel#qt_wizard_subtitle {{
                background-color: {"#F3F4F6" if t.is_light() else t.surface};
                color: {t.text_secondary};
                padding: 8px 24px 16px 24px;
            }}
            
            QWizard QWidget#qt_wizard_header {{
                background-color: {"#F3F4F6" if t.is_light() else t.surface};
                border-bottom: {"1px solid #E5E7EB" if t.is_light() else f"1px solid {t.border}"};
            }}
            
            /* ============ Tooltips ============ */
            QToolTip {{
                background-color: {t.surface};
                color: {t.foreground};
                border: 1px solid {t.border};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 12px;
            }}
            
            /* ============ Progress Bar ============ */
            QProgressBar {{
                background-color: {t.surface_hover};
                border: none;
                border-radius: 4px;
                height: 8px;
                text-align: center;
            }}
            
            QProgressBar::chunk {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 {t.primary}, stop:1 {t.accent});
                border-radius: 4px;
            }}
            
            /* ============ Slider ============ */
            QSlider::groove:horizontal {{
                background-color: {t.surface_hover};
                height: 6px;
                border-radius: 3px;
            }}
            
            QSlider::handle:horizontal {{
                background-color: {t.primary};
                width: 16px;
                height: 16px;
                margin: -5px 0;
                border-radius: 8px;
            }}
            
            QSlider::handle:horizontal:hover {{
                background-color: {t.accent};
            }}
            
            """
