"""
Reusable widget classes and helpers for the Data Tab.

Contains the column picker, list box, and Y-axis item widgets, along
with the shared constants and helper functions used by DataTab.
"""

from __future__ import annotations

from typing import List, Dict, Set

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QToolButton, QCompleter,
)
from PySide6.QtCore import Qt, Signal, QStringListModel
from PySide6.QtGui import QKeyEvent

from ...core.state import AggregationType


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_INDEX_SENTINEL = "(Index)"
_AGG_ITEMS: List[tuple[str, AggregationType]] = [
    ("SUM", AggregationType.SUM),
    ("MEAN", AggregationType.MEAN),
    ("MEDIAN", AggregationType.MEDIAN),
    ("MIN", AggregationType.MIN),
    ("MAX", AggregationType.MAX),
    ("COUNT", AggregationType.COUNT),
    ("STD", AggregationType.STD),
    ("VAR", AggregationType.VAR),
    ("FIRST", AggregationType.FIRST),
    ("LAST", AggregationType.LAST),
]

_YAXIS_MAX_HEIGHT = 150
_GROUP_MAX_HEIGHT = 100
_HOVER_MAX_HEIGHT = 100
_FILTER_MAX_HEIGHT = 150


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_separator() -> QFrame:
    """Create a horizontal line separator."""
    line = QFrame()
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    line.setObjectName("dataTabSeparator")
    line.setFixedHeight(2)
    return line


def _make_section_header(
    title: str,
    on_none: object = None,
) -> tuple:
    """Return (QHBoxLayout, btn_none | None) with *title* label and [None] button."""
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(4)

    label = QLabel(title)
    label.setObjectName("sectionHeader")
    row.addWidget(label)
    row.addStretch()

    btn_none = None
    if on_none is not None:
        btn_none = QPushButton("None")
        btn_none.setObjectName("smallButton")
        btn_none.setFixedHeight(20)
        btn_none.setMaximumWidth(42)
        btn_none.setToolTip("Deselect all items in this section")
        btn_none.clicked.connect(on_none)
        row.addWidget(btn_none)

    return row, btn_none


def _is_numeric_dtype(dtype_str: str) -> bool:
    """Return *True* if *dtype_str* (Polars string repr) is numeric."""
    dtype_lower = dtype_str.lower()
    numeric_keywords = (
        "int", "float", "decimal", "uint",
        "i8", "i16", "i32", "i64",
        "u8", "u16", "u32", "u64",
        "f32", "f64",
    )
    return any(kw in dtype_lower for kw in numeric_keywords)


# ---------------------------------------------------------------------------
# Reusable widgets: _SearchableColumnPicker and _ColumnListBox
# ---------------------------------------------------------------------------

class _SearchableColumnPicker(QWidget):
    """Searchable combo: type to filter (contains match), click arrow for full dropdown.

    When the user selects a column (Enter or click), ``column_selected``
    is emitted and the text is cleared.
    """

    column_selected = Signal(str)

    def __init__(self, placeholder: str = "🔍 Search columns...", parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._combo = QComboBox()
        self._combo.setEditable(True)
        self._combo.setInsertPolicy(QComboBox.NoInsert)
        self._combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._combo.setMinimumHeight(28)
        if self._combo.lineEdit():
            self._combo.lineEdit().setPlaceholderText(placeholder)

        # Contains-match completer for search-as-you-type
        self._completer = QCompleter()
        self._completer.setCaseSensitivity(Qt.CaseInsensitive)
        self._completer.setFilterMode(Qt.MatchContains)
        self._completer.setCompletionMode(QCompleter.PopupCompletion)
        self._combo.setCompleter(self._completer)

        self._combo.activated.connect(self._on_activated)
        # Also handle completer selection (Enter on filtered result)
        self._completer.activated.connect(self._on_completer_activated)
        layout.addWidget(self._combo)

        self._model = QStringListModel()
        self._completer.setModel(self._model)

        self._all_items: List[str] = []
        self._excluded: Set[str] = set()

    def set_items(self, items: List[str]) -> None:
        """Set the full list of available items."""
        self._all_items = list(items)
        self._refresh_combo()

    def set_excluded(self, excluded: Set[str]) -> None:
        """Set items that should be excluded (already selected)."""
        self._excluded = set(excluded)
        self._refresh_combo()

    def _refresh_combo(self) -> None:
        visible = [item for item in self._all_items if item not in self._excluded]
        self._combo.blockSignals(True)
        self._combo.clear()
        for item in visible:
            self._combo.addItem(item)
        self._combo.setCurrentIndex(-1)
        if self._combo.lineEdit():
            self._combo.lineEdit().clear()
        self._combo.blockSignals(False)
        # Update completer model
        self._model.setStringList(visible)

    def _on_activated(self, index: int) -> None:
        text = self._combo.itemText(index)
        self._emit_selection(text)

    def _on_completer_activated(self, text: str) -> None:
        self._emit_selection(text)

    def _emit_selection(self, text: str) -> None:
        if text and text not in self._excluded:
            self.column_selected.emit(text)
            # Clear text after selection
            self._combo.setCurrentIndex(-1)
            if self._combo.lineEdit():
                self._combo.lineEdit().clear()

    def setToolTip(self, tip: str) -> None:  # type: ignore[override]
        """Forward tooltip to both the outer widget and the inner combo."""
        super().setToolTip(tip)
        self._combo.setToolTip(tip)

    def clear_text(self) -> None:
        self._combo.setCurrentIndex(-1)
        if self._combo.lineEdit():
            self._combo.lineEdit().clear()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # type: ignore[override]
        """Escape clears the search box; other keys pass through normally."""
        if event.key() == Qt.Key_Escape:
            self.clear_text()
            event.accept()
        else:
            super().keyPressEvent(event)


class _ListBoxItem(QWidget):
    """Single item in a _ColumnListBox with a label and [×] remove button."""

    remove_clicked = Signal(str)

    def __init__(self, text: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.item_text = text
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(4)

        self._label = QLabel(text)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self._label, 1)

        self._remove_btn = QPushButton("×")
        self._remove_btn.setObjectName("smallButton")
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.setToolTip("Remove this item")
        self._remove_btn.setAccessibleName(f"Remove {text}")
        self._remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.item_text))
        layout.addWidget(self._remove_btn)

    def label_text(self) -> str:
        return self.item_text


class _ColumnListBox(QWidget):
    """Scrollable list of items with [×] remove buttons.

    Signals
    -------
    item_added : str
    item_removed : str
    """

    item_added = Signal(str)
    item_removed = Signal(str)

    def __init__(self, max_height: int = 100, parent: QWidget | None = None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll.setMaximumHeight(max_height)
        self._scroll.setFrameShape(QFrame.NoFrame)

        self._container = QWidget()
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)
        self._layout.addStretch()

        self._scroll.setWidget(self._container)
        outer.addWidget(self._scroll)

        self._items: Dict[str, _ListBoxItem] = {}

    def add_item(self, text: str) -> None:
        """Add an item to the list. No-op if already present."""
        if text in self._items:
            return
        item_w = _ListBoxItem(text)
        item_w.remove_clicked.connect(self._on_remove)
        self._items[text] = item_w
        self._layout.insertWidget(self._layout.count() - 1, item_w)
        self.item_added.emit(text)

    def remove_item(self, text: str) -> None:
        """Remove an item by text."""
        item_w = self._items.pop(text, None)
        if item_w is not None:
            item_w.setParent(None)
            item_w.deleteLater()
            self.item_removed.emit(text)

    def clear_all(self) -> None:
        """Remove all items."""
        for text in list(self._items.keys()):
            self.remove_item(text)

    def items(self) -> List[str]:
        """Return list of current item texts, in insertion order."""
        return list(self._items.keys())

    def count(self) -> int:
        return len(self._items)

    def contains(self, text: str) -> bool:
        return text in self._items

    def _on_remove(self, text: str) -> None:
        self.remove_item(text)


# ---------------------------------------------------------------------------
# Per-item widgets used inside the Y-Axis section (ListBox version)
# ---------------------------------------------------------------------------

class _YAxisListItem(QWidget):
    """Single Y-Axis column entry in the list with formula toggle and [×] button."""

    remove_clicked = Signal(str)
    formula_changed = Signal(str, str)  # column_name, formula_text

    def __init__(self, column_name: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.column_name = column_name
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 1, 4, 1)
        layout.setSpacing(2)

        # Row 1 – column name + formula toggle + remove button
        row1 = QHBoxLayout()
        row1.setSpacing(4)

        self._label = QLabel(self.column_name)
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        row1.addWidget(self._label, 1)

        self.formula_toggle = QToolButton()
        self.formula_toggle.setText("▶ f(y)")
        self.formula_toggle.setCheckable(True)
        self.formula_toggle.setChecked(False)
        self.formula_toggle.setMinimumHeight(20)
        self.formula_toggle.setToolTip("Toggle formula editor for this column")
        self.formula_toggle.clicked.connect(self._on_formula_toggled)
        row1.addWidget(self.formula_toggle)

        self._remove_btn = QPushButton("×")
        self._remove_btn.setObjectName("smallButton")
        self._remove_btn.setFixedSize(20, 20)
        self._remove_btn.setToolTip("Remove this column")
        self._remove_btn.setAccessibleName(f"Remove {self.column_name} from Y-Axis")
        self._remove_btn.clicked.connect(lambda: self.remove_clicked.emit(self.column_name))
        row1.addWidget(self._remove_btn)

        layout.addLayout(row1)

        # Row 2 – formula input + error label (hidden by default)
        self.formula_widget = QWidget()
        formula_vbox = QVBoxLayout(self.formula_widget)
        formula_vbox.setContentsMargins(20, 0, 0, 0)
        formula_vbox.setSpacing(2)

        formula_input_row = QHBoxLayout()
        formula_input_row.setSpacing(4)
        self.formula_edit = QLineEdit()
        self.formula_edit.setPlaceholderText("f(y)=...  e.g. y*2, LOG(y)")
        self.formula_edit.setMinimumHeight(24)
        self.formula_edit.editingFinished.connect(self._on_formula_finished)
        formula_input_row.addWidget(self.formula_edit)
        formula_vbox.addLayout(formula_input_row)

        self._formula_error_label = QLabel()
        self._formula_error_label.setObjectName("formulaErrorLabel")
        self._formula_error_label.setStyleSheet("color: #EF4444; font-size: 11px;")
        self._formula_error_label.setWordWrap(True)
        self._formula_error_label.setVisible(False)
        formula_vbox.addWidget(self._formula_error_label)

        layout.addWidget(self.formula_widget)
        self.formula_widget.setVisible(False)

    def _on_formula_toggled(self, checked: bool) -> None:
        self.formula_widget.setVisible(checked)
        self.formula_toggle.setText("▼ f(y)" if checked else "▶ f(y)")

    def _on_formula_finished(self) -> None:
        formula = self.formula_edit.text().strip()
        if formula:
            error = self._validate_formula_syntax(formula)
            if error:
                self.formula_edit.setStyleSheet("border: 1px solid #EF4444;")
                self._formula_error_label.setText(f"\u26a0 {error}")
                self._formula_error_label.setVisible(True)
                return
        # Valid (or empty) — clear any previous error state
        self.formula_edit.setStyleSheet("")
        self._formula_error_label.setVisible(False)
        self.formula_changed.emit(self.column_name, formula)

    @staticmethod
    def _validate_formula_syntax(formula: str) -> str:
        """Return an error message string if *formula* has a syntax problem, else ''."""
        import ast as _ast
        import re as _re
        # Replace {col} references with placeholder identifiers so ast.parse works
        normalised = _re.sub(r"\{[^}]+\}", "_col_", formula)
        # Replace common math functions with identifiers
        normalised = _re.sub(r"\b(LOG|SQRT|ABS|EXP|SIN|COS|TAN|ROUND|CEIL|FLOOR)\b",
                             "func", normalised, flags=_re.IGNORECASE)
        # Treat bare 'y' as the column placeholder
        normalised = normalised.replace("y", "_col_").replace("Y", "_col_")
        try:
            _ast.parse(normalised, mode="eval")
        except SyntaxError as exc:
            return f"Syntax error: {exc.msg}"
        return ""

    def set_formula(self, formula: str) -> None:
        self.formula_edit.setText(formula)
        # Clear any previous error state when formula is set programmatically
        self.formula_edit.setStyleSheet("")
        self._formula_error_label.setVisible(False)
        if formula:
            self.formula_toggle.setChecked(True)
            self.formula_widget.setVisible(True)
            self.formula_toggle.setText("▼ f(y)")

    def get_formula(self) -> str:
        return self.formula_edit.text().strip()


# ---------------------------------------------------------------------------
# Kept for backward compatibility — old _YAxisItemWidget is no longer used
# by the new UI but some test code may reference the class.
# ---------------------------------------------------------------------------

_YAxisItemWidget = _YAxisListItem  # alias
