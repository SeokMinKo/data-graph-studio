from __future__ import annotations

import re
from typing import Dict, List, Tuple

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


class SplitColumnDialog(QDialog):
    """Dialog for splitting a source column using regex capture groups."""

    def __init__(
        self,
        source_column: str,
        sample_values: List[str],
        existing_columns: List[str],
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Split Column")
        self.setMinimumWidth(620)

        self._source_column = source_column
        self._sample_values = [str(v) for v in sample_values if v is not None][:5]
        self._existing_columns = set(existing_columns)
        self._mapping_rows: List[Tuple[str, QLineEdit]] = []

        self._build_ui()
        self._refresh_from_pattern()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        form = QFormLayout()

        self._source_edit = QLineEdit(self._source_column)
        self._source_edit.setReadOnly(True)
        form.addRow("Source Column:", self._source_edit)

        self._pattern_edit = QLineEdit()
        self._pattern_edit.setPlaceholderText(r"e.g. (?P<dev>\\w+)=(?P<dev_id>\\d+)")
        self._pattern_edit.textChanged.connect(self._refresh_from_pattern)
        form.addRow("Regex Pattern:", self._pattern_edit)

        layout.addLayout(form)

        mapping_group = QGroupBox("New Column Mapping")
        self._mapping_layout = QFormLayout(mapping_group)
        layout.addWidget(mapping_group)

        self._preview = QTextEdit()
        self._preview.setReadOnly(True)
        self._preview.setPlaceholderText("Preview will appear here")
        layout.addWidget(QLabel("Sample Preview:"))
        layout.addWidget(self._preview)

        self._error_label = QLabel("")
        self._error_label.setStyleSheet("color: #d9534f;")
        layout.addWidget(self._error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _clear_mapping_rows(self):
        while self._mapping_layout.count():
            item = self._mapping_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._mapping_rows.clear()

    def _refresh_from_pattern(self):
        pattern = self._pattern_edit.text().strip()
        self._error_label.clear()
        self._clear_mapping_rows()
        self._preview.clear()

        if not pattern:
            return

        try:
            compiled = re.compile(pattern)
        except re.error as e:
            self._error_label.setText(f"Regex error: {e}")
            return

        groups = self._resolved_groups(compiled)
        if not groups:
            self._error_label.setText(
                "Pattern must include at least one capture group."
            )
            return

        for idx, group_name in groups:
            if group_name:
                default_name = group_name
                label = f"Group {idx} ({group_name})"
            else:
                default_name = f"{self._source_column}_g{idx}"
                label = f"Group {idx}"

            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)

            edit = QLineEdit(default_name)
            edit.setPlaceholderText(default_name)
            row_layout.addWidget(edit)

            self._mapping_layout.addRow(label + ":", row)
            self._mapping_rows.append(
                (f"g{idx}" if not group_name else group_name, edit)
            )

        preview_lines: List[str] = []
        for raw in self._sample_values:
            m = compiled.search(raw)
            if not m:
                preview_lines.append(f"{raw}  ->  (no match)")
                continue

            parts = []
            for idx, group_name in groups:
                key = group_name if group_name else f"g{idx}"
                value = m.group(idx)
                parts.append(f"{key}={value}")
            preview_lines.append(f"{raw}  ->  " + ", ".join(parts))

        self._preview.setPlainText("\n".join(preview_lines))

    def _resolved_groups(self, compiled: re.Pattern) -> List[Tuple[int, str]]:
        if compiled.groups <= 0:
            return []

        named_by_idx = {idx: name for name, idx in compiled.groupindex.items()}
        groups: List[Tuple[int, str]] = []
        for idx in range(1, compiled.groups + 1):
            groups.append((idx, named_by_idx.get(idx, "")))
        return groups

    def _on_accept(self):
        try:
            self.get_payload()
        except ValueError as e:
            QMessageBox.warning(self, "Split Column", str(e))
            return
        self.accept()

    def get_payload(self) -> Dict[str, object]:
        pattern = self._pattern_edit.text().strip()
        if not pattern:
            raise ValueError("Regex pattern is required.")

        try:
            compiled = re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {e}") from e

        groups = self._resolved_groups(compiled)
        if not groups:
            raise ValueError("Pattern must include at least one capture group.")

        mapping: Dict[int, str] = {}
        used = set()

        if len(self._mapping_rows) != len(groups):
            raise ValueError(
                "Group mapping is out of sync. Please re-check the pattern."
            )

        for (idx, _group_name), (_key, edit) in zip(groups, self._mapping_rows):
            new_name = edit.text().strip()
            if not new_name:
                raise ValueError("New column names cannot be empty.")
            if new_name in used:
                raise ValueError(f"Duplicate target column name: {new_name}")
            if new_name in self._existing_columns and new_name != self._source_column:
                raise ValueError(f"Target column already exists: {new_name}")
            used.add(new_name)
            mapping[idx] = new_name

        return {
            "source": self._source_column,
            "pattern": pattern,
            "mapping": mapping,
        }
