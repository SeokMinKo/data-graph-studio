"""PivotTableDialog - F9 pivot table creation dialog."""

import logging
from typing import Optional


import polars as pl

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QFormLayout, QComboBox, QPushButton,
    QTableView, QDialogButtonBox, QMessageBox,
)

from ._polars_table_model import PolarsTableModel


logger = logging.getLogger(__name__)

class PivotTableDialog(QDialog):
    """Dialog for creating pivot tables from data."""

    def __init__(self, df: pl.DataFrame, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Pivot Table")
        self.setMinimumSize(500, 400)
        self._df = df
        self._result_df: Optional[pl.DataFrame] = None

        layout = QVBoxLayout(self)
        form = QFormLayout()

        columns = df.columns

        self.index_combo = QComboBox()
        self.index_combo.addItems(columns)
        form.addRow("Row (Index):", self.index_combo)

        self.columns_combo = QComboBox()
        self.columns_combo.addItems(columns)
        if len(columns) > 1:
            self.columns_combo.setCurrentIndex(1)
        form.addRow("Column:", self.columns_combo)

        self.values_combo = QComboBox()
        # Only numeric columns for values
        numeric_cols = [c for c in columns if df[c].dtype.is_numeric()]
        self.values_combo.addItems(numeric_cols if numeric_cols else columns)
        form.addRow("Values:", self.values_combo)

        self.agg_combo = QComboBox()
        self.agg_combo.addItems(["first", "sum", "mean", "count", "min", "max"])
        self.agg_combo.setCurrentText("sum")
        form.addRow("Aggregation:", self.agg_combo)

        layout.addLayout(form)

        # Preview button
        preview_btn = QPushButton("Preview")
        preview_btn.clicked.connect(self._preview)
        layout.addWidget(preview_btn)

        # Result table
        self.result_view = QTableView()
        self.result_model = PolarsTableModel()
        self.result_view.setModel(self.result_model)
        layout.addWidget(self.result_view)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _preview(self):
        try:
            idx = self.index_combo.currentText()
            cols = self.columns_combo.currentText()
            vals = self.values_combo.currentText()
            agg = self.agg_combo.currentText()

            self._result_df = self._df.pivot(
                values=vals, index=idx, on=cols,
                aggregate_function=agg
            )
            self.result_model.set_dataframe(self._result_df)
        except Exception as e:
            logger.exception("pivot_table_dialog.compute_pivot.error")
            QMessageBox.warning(self, "Pivot Error", str(e))

    def get_result(self) -> Optional[pl.DataFrame]:
        return self._result_df
