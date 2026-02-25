"""DataTableView - custom QTableView for the table panel."""

from typing import List, Tuple

from PySide6.QtWidgets import (
    QTableView, QAbstractItemView, QMenu, QApplication,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QKeySequence


class DataTableView(QTableView):
    """데이터 테이블 뷰 - Minimal Design"""

    column_dragged = Signal(str)
    column_action = Signal(str)
    rows_selected = Signal(list)
    exclude_value = Signal(str, object)  # column, value
    hide_column = Signal(str)  # column name
    exclude_column = Signal(str)  # column name (drop from data)
    column_order_changed = Signal(list)
    column_type_convert = Signal(str, str)  # column_name, target_type
    column_freeze = Signal(str)  # column name
    column_unfreeze = Signal(str)  # column name
    conditional_format_requested = Signal(str)  # column name
    split_column_requested = Signal(str)  # column name
    multi_sort_requested = Signal(int, object)  # column, Qt.SortOrder

    def __init__(self):
        super().__init__()

        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setSortingEnabled(True)
        self.setDragEnabled(True)

        # Styles handled by global theme stylesheet
        self.setObjectName("dataTableView")

        # Context menu for cells
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_cell_menu)

        self.horizontalHeader().setStretchLastSection(True)
        self.horizontalHeader().setSectionsMovable(True)
        self.horizontalHeader().setContextMenuPolicy(Qt.CustomContextMenu)
        self.horizontalHeader().customContextMenuRequested.connect(self._show_header_menu)
        self.horizontalHeader().sectionPressed.connect(self._on_header_pressed)
        self.horizontalHeader().sectionMoved.connect(self._on_header_moved)
        self.horizontalHeader().installEventFilter(self)

        # Multi-sort state
        self._pending_multi_sort: List[Tuple[int, Qt.SortOrder]] = []

    def setModel(self, model):
        """Bug 4: Reconnect selectionModel on every model swap."""
        super().setModel(model)
        sel_model = self.selectionModel()
        if sel_model:
            sel_model.selectionChanged.connect(self._on_selection_changed)

    # F1: Multi-cell Ctrl+C copy
    def keyPressEvent(self, event):
        if event.matches(QKeySequence.Copy):
            self._copy_selection_to_clipboard()
            return
        super().keyPressEvent(event)

    def _copy_selection_to_clipboard(self):
        """Copy selected cells as TSV to clipboard."""
        sel = self.selectionModel()
        if not sel:
            return
        indexes = sel.selectedIndexes()
        if not indexes:
            return
        rows = sorted(set(idx.row() for idx in indexes))
        cols = sorted(set(idx.column() for idx in indexes))
        lines = []
        for r in rows:
            line = []
            for c in cols:
                idx = self.model().index(r, c)
                line.append(str(self.model().data(idx, Qt.DisplayRole) or ""))
            lines.append("\t".join(line))
        QApplication.clipboard().setText("\n".join(lines))

    def _on_header_pressed(self, logical_index: int):
        # Store column name for context menu / reorder
        pass

    def _on_header_moved(self, logical_index: int, old_visual_index: int, new_visual_index: int):
        model = self.model()
        header = self.horizontalHeader()
        if not model or not header:
            return
        order = []
        for visual in range(header.count()):
            logical = header.logicalIndex(visual)
            name = model.get_column_name(logical)
            if name:
                order.append(name)
        if order:
            self.column_order_changed.emit(order)

    def eventFilter(self, obj, event):
        # Ctrl+drag to zones removed (zones moved to Data tab in Chart Options)
        return super().eventFilter(obj, event)

    def _on_selection_changed(self, selected, deselected):
        indexes = self.selectionModel().selectedRows()
        rows = [idx.row() for idx in indexes]
        self.rows_selected.emit(rows)

    def _show_header_menu(self, pos):
        logical_index = self.horizontalHeader().logicalIndexAt(pos)
        model = self.model()
        if not model:
            return

        column_name = model.get_column_name(logical_index)
        if not column_name:
            return

        menu = QMenu(self)

        # Set as — 최상위에 펼쳐서 배치
        set_x = QAction("📐 Set as X-Axis", self)
        set_x.triggered.connect(lambda: self.column_dragged.emit(f"X:{column_name}"))
        menu.addAction(set_x)

        set_y = QAction("📊 Set as Y-Axis Value", self)
        set_y.triggered.connect(lambda: self.column_dragged.emit(f"V:{column_name}"))
        menu.addAction(set_y)

        set_g = QAction("📁 Set as Group By", self)
        set_g.triggered.connect(lambda: self.column_dragged.emit(f"G:{column_name}"))
        menu.addAction(set_g)

        set_h = QAction("💬 Set as Hover Data", self)
        set_h.triggered.connect(lambda: self.column_dragged.emit(f"H:{column_name}"))
        menu.addAction(set_h)

        menu.addSeparator()

        sort_asc = QAction("↑ Sort Ascending", self)
        sort_asc.triggered.connect(lambda: self.sortByColumn(logical_index, Qt.AscendingOrder))
        menu.addAction(sort_asc)

        sort_desc = QAction("↓ Sort Descending", self)
        sort_desc.triggered.connect(lambda: self.sortByColumn(logical_index, Qt.DescendingOrder))
        menu.addAction(sort_desc)

        menu.addSeparator()

        exclude_col = QAction("🚫 Exclude Column", self)
        exclude_col.triggered.connect(lambda: self.exclude_column.emit(column_name))
        menu.addAction(exclude_col)

        menu.addSeparator()

        # F5: Convert Type submenu
        type_menu = menu.addMenu("🔄 Convert Type")
        for dtype_name in ["Int64", "Float64", "String", "Date", "Boolean"]:
            act = QAction(dtype_name, self)
            act.triggered.connect(lambda checked=False, t=dtype_name: self.column_type_convert.emit(column_name, t))
            type_menu.addAction(act)

        # F3: Conditional Formatting
        cond_fmt = QAction("🎨 Conditional Formatting...", self)
        cond_fmt.triggered.connect(lambda: self.conditional_format_requested.emit(column_name))
        menu.addAction(cond_fmt)

        split_col = QAction("✂️ Split Column by Regex...", self)
        split_col.triggered.connect(lambda: self.split_column_requested.emit(column_name))
        menu.addAction(split_col)

        # F7: Freeze/Unfreeze Column
        freeze_act = QAction("📌 Freeze Column", self)
        freeze_act.triggered.connect(lambda: self.column_freeze.emit(column_name))
        menu.addAction(freeze_act)

        unfreeze_act = QAction("📌 Unfreeze Column", self)
        unfreeze_act.triggered.connect(lambda: self.column_unfreeze.emit(column_name))
        menu.addAction(unfreeze_act)

        menu.exec(self.horizontalHeader().mapToGlobal(pos))

    def _show_cell_menu(self, pos):
        """셀 우클릭 메뉴"""
        index = self.indexAt(pos)
        if not index.isValid():
            return

        model = self.model()
        if not model:
            return

        column_name = model.get_column_name(index.column())
        cell_value = model.data(index, Qt.DisplayRole)

        if not column_name:
            return

        menu = QMenu(self)

        # Filter options
        if cell_value:
            display_val = str(cell_value)[:20] + "..." if len(str(cell_value)) > 20 else str(cell_value)

            filter_eq = QAction(f"🔍 Filter: {column_name} = \"{display_val}\"", self)
            filter_eq.triggered.connect(lambda: self.exclude_value.emit(column_name, ("eq", cell_value)))
            menu.addAction(filter_eq)

            filter_ne = QAction(f"🚫 Exclude: {column_name} ≠ \"{display_val}\"", self)
            filter_ne.triggered.connect(lambda: self.exclude_value.emit(column_name, ("ne", cell_value)))
            menu.addAction(filter_ne)

            menu.addSeparator()

        # Copy
        copy_action = QAction("📋 Copy", self)
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(str(cell_value) if cell_value else ""))
        menu.addAction(copy_action)

        menu.exec(self.viewport().mapToGlobal(pos))
