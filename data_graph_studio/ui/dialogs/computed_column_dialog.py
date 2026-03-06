"""
ComputedColumnDialog — PRD §5.3

Dialog for creating computed columns:
- Formula, Moving Average, Difference, Cumsum, Normalize
- Preview (first rows)
- Error highlighting (FR-3.9)
- Progress bar + Cancel for long computations (NFR-3.2)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import List, Optional

import polars as pl
from PySide6.QtCore import Signal, QThread, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QFormLayout,
    QLineEdit,
    QRadioButton,
    QButtonGroup,
    QSpinBox,
    QComboBox,
    QTextEdit,
    QLabel,
    QDialogButtonBox,
    QProgressBar,
    QGroupBox,
    QWidget,
)

from data_graph_studio.core.formula_parser import (
    FormulaParser,
    FormulaError,
    FormulaSecurityError,
    FormulaColumnError,
    FormulaTypeError,
)

logger = logging.getLogger(__name__)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data structures
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


@dataclass
class ComputedColumn:
    """PRD §6.3 — definition of a computed column."""

    name: str
    kind: str  # "formula" | "moving_avg" | "difference" | "cumsum" | "normalize"
    expression: str  # formula string or source column
    params: dict = field(default_factory=dict)
    dataset_id: str = ""
    depends_on: List[str] = field(default_factory=list)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Worker thread for heavy computation (NFR-3.2, §10.5)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ComputeWorker(QThread):
    """Run computed column evaluation in a background thread."""

    finished = Signal(object)  # pl.Series or None
    error = Signal(str)  # error message
    progress = Signal(int)  # 0-100

    def __init__(
        self,
        parser: FormulaParser,
        definition: ComputedColumn,
        df: pl.DataFrame,
        parent=None,
    ):
        super().__init__(parent)
        self._parser = parser
        self._definition = definition
        self._df = df
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            self.progress.emit(10)
            defn = self._definition

            if self._cancelled:
                self.finished.emit(None)
                return

            if defn.kind == "formula":
                result = self._parser.evaluate(defn.expression, self._df)
            elif defn.kind == "moving_avg":
                window = defn.params.get("window", 3)
                result = self._parser.evaluate_moving_avg(
                    defn.expression, window, self._df
                )
            elif defn.kind == "difference":
                order = defn.params.get("order", 1)
                result = self._parser.evaluate_diff(defn.expression, order, self._df)
            elif defn.kind == "cumsum":
                result = self._parser.evaluate_cumsum(defn.expression, self._df)
            elif defn.kind == "normalize":
                method = defn.params.get("method", "min_max")
                result = self._parser.evaluate_normalize(
                    defn.expression, method, self._df
                )
            else:
                self.error.emit(f"Unknown kind: {defn.kind}")
                return

            if self._cancelled:
                self.finished.emit(None)
                return

            self.progress.emit(100)
            self.finished.emit(result)

        except (
            FormulaError,
            FormulaSecurityError,
            FormulaColumnError,
            FormulaTypeError,
        ) as e:
            self.error.emit(str(e))
        except Exception as e:
            self.error.emit(f"Unexpected error: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dialog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━


class ComputedColumnDialog(QDialog):
    """
    PRD §5.3 — "Add Computed Column" dialog.

    Emits column_created(ComputedColumn, pl.Series) on success.
    """

    column_created = Signal(object, object)  # (ComputedColumn, pl.Series)

    def __init__(
        self,
        df: pl.DataFrame,
        existing_columns: Optional[List[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Add Computed Column")
        self.setMinimumWidth(480)
        self._df = df
        self._existing_columns = existing_columns or list(df.columns)
        self._parser = FormulaParser()
        self._worker: Optional[ComputeWorker] = None
        self._result_series: Optional[pl.Series] = None

        self._build_ui()

    # ── UI Construction ───────────────────────────────────────

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # Name
        form = QFormLayout()
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. power_calc")
        self._name_edit.setToolTip("Name for the new computed column")
        form.addRow("Name:", self._name_edit)
        layout.addLayout(form)

        # Type selection
        type_group = QGroupBox("Type")
        type_layout = QVBoxLayout(type_group)
        self._type_group = QButtonGroup(self)

        self._radio_formula = QRadioButton("Formula")
        self._radio_formula.setToolTip(
            "Create column using a custom formula expression"
        )
        self._radio_moving_avg = QRadioButton("Moving Average")
        self._radio_moving_avg.setToolTip("Compute moving average over a window")
        self._radio_diff = QRadioButton("Difference")
        self._radio_diff.setToolTip("Compute difference between consecutive values")
        self._radio_cumsum = QRadioButton("Cumulative Sum")
        self._radio_cumsum.setToolTip("Compute running cumulative sum")
        self._radio_normalize = QRadioButton("Normalize")
        self._radio_normalize.setToolTip("Normalize values using min-max or z-score")

        for i, rb in enumerate(
            [
                self._radio_formula,
                self._radio_moving_avg,
                self._radio_diff,
                self._radio_cumsum,
                self._radio_normalize,
            ]
        ):
            self._type_group.addButton(rb, i)
            type_layout.addWidget(rb)

        self._radio_formula.setChecked(True)
        layout.addWidget(type_group)

        # Parameters area (stacked)
        self._param_stack = QWidget()
        param_layout = QVBoxLayout(self._param_stack)
        param_layout.setContentsMargins(0, 0, 0, 0)

        # Formula input
        self._formula_edit = QLineEdit()
        self._formula_edit.setPlaceholderText("{voltage} * {current}")
        self._formula_edit.setToolTip("Enter formula using {column_name} syntax")
        param_layout.addWidget(QLabel("Formula:"))
        param_layout.addWidget(self._formula_edit)

        # Source column combo
        self._source_combo = QComboBox()
        self._source_combo.setToolTip("Select the source column for computation")
        self._source_combo.addItems(self._existing_columns)
        param_layout.addWidget(QLabel("Source Column:"))
        param_layout.addWidget(self._source_combo)

        # Window size
        self._window_spin = QSpinBox()
        self._window_spin.setToolTip("Number of rows in the moving average window")
        self._window_spin.setRange(1, 100000)
        self._window_spin.setValue(3)
        param_layout.addWidget(QLabel("Window Size:"))
        param_layout.addWidget(self._window_spin)

        # Diff order
        self._order_spin = QSpinBox()
        self._order_spin.setToolTip("Order of differencing (1 = first difference)")
        self._order_spin.setRange(1, 10)
        self._order_spin.setValue(1)
        param_layout.addWidget(QLabel("Diff Order:"))
        param_layout.addWidget(self._order_spin)

        # Normalize method
        self._norm_combo = QComboBox()
        self._norm_combo.setToolTip("Normalization method: min-max (0-1) or z-score")
        self._norm_combo.addItems(["min_max", "z_score"])
        param_layout.addWidget(QLabel("Method:"))
        param_layout.addWidget(self._norm_combo)

        layout.addWidget(self._param_stack)

        # Error display (FR-3.9)
        self._error_label = QLabel()
        self._error_label.setStyleSheet("color: red; font-size: 12px;")
        self._error_label.setWordWrap(True)
        self._error_label.hide()
        layout.addWidget(self._error_label)

        # Preview
        self._preview_label = QLabel("Preview:")
        self._preview_text = QTextEdit()
        self._preview_text.setReadOnly(True)
        self._preview_text.setToolTip("Preview of computed values (first 10 rows)")
        self._preview_text.setMaximumHeight(80)
        layout.addWidget(self._preview_label)
        layout.addWidget(self._preview_text)

        # Progress bar (NFR-3.2)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.hide()
        layout.addWidget(self._progress_bar)

        # Buttons
        self._btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        ok_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Ok)
        if ok_btn:
            ok_btn.setToolTip("Create the computed column")
        cancel_btn = self._btn_box.button(QDialogButtonBox.StandardButton.Cancel)
        if cancel_btn:
            cancel_btn.setToolTip("Cancel and close dialog")
        self._btn_box.accepted.connect(self._on_create)
        self._btn_box.rejected.connect(self._on_cancel)
        layout.addWidget(self._btn_box)

        # Debounce timer for preview (FR-B3.6: 300ms debounce)
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(300)
        self._preview_timer.timeout.connect(self._update_preview)

        # Connections
        self._type_group.idClicked.connect(self._on_type_changed)
        self._formula_edit.textChanged.connect(self._on_formula_changed)

    # ── Slots ─────────────────────────────────────────────────

    def _on_type_changed(self, type_id: int):
        """Update visible parameters based on selected type."""
        self._clear_error()
        self._preview_timer.start()  # trigger preview update

    def _on_formula_changed(self, text: str):
        """Formula text changed — debounce preview (FR-B3.6)."""
        self._clear_error()
        self._preview_timer.start()

    def _update_preview(self):
        """Compute preview on 100-row sample (FR-B3.6)."""
        name = self._name_edit.text().strip() or "_preview"
        defn = self._build_definition(name)
        if defn is None:
            self._preview_text.clear()
            return

        # Sample max 100 rows
        sample_df = self._df.head(100) if len(self._df) > 100 else self._df
        try:
            worker_defn = defn
            if worker_defn.kind == "formula":
                result = self._parser.evaluate(worker_defn.expression, sample_df)
            elif worker_defn.kind == "moving_avg":
                result = self._parser.evaluate_moving_avg(
                    worker_defn.expression,
                    worker_defn.params.get("window", 3),
                    sample_df,
                )
            elif worker_defn.kind == "difference":
                result = self._parser.evaluate_diff(
                    worker_defn.expression,
                    worker_defn.params.get("order", 1),
                    sample_df,
                )
            elif worker_defn.kind == "cumsum":
                result = self._parser.evaluate_cumsum(worker_defn.expression, sample_df)
            elif worker_defn.kind == "normalize":
                result = self._parser.evaluate_normalize(
                    worker_defn.expression,
                    worker_defn.params.get("method", "min_max"),
                    sample_df,
                )
            else:
                self._preview_text.setText("Unknown type")
                return
            preview_vals = result.head(10).to_list()
            self._preview_text.setText(str(preview_vals))
        except FormulaColumnError as e:
            self._show_error(f"컬럼 없음: {e}")
        except FormulaTypeError as e:
            self._show_error(f"타입 불일치: {e}")
        except FormulaSecurityError as e:
            self._show_error(str(e))
        except FormulaError as e:
            self._show_error(f"표현식 문법 오류: {e}")
        except ZeroDivisionError:
            self._show_error("0으로 나누기")
        except Exception as e:
            self._show_error(str(e))

    def _clear_error(self):
        self._error_label.hide()

    def _show_error(self, msg: str):
        """Show inline error with red highlight (FR-B3.4)."""
        self._error_label.setText(f"⚠ {msg}")
        self._error_label.setStyleSheet(
            "color: #EF4444; font-size: 12px; padding: 4px; "
            "background: rgba(239,68,68,0.1); border-radius: 3px;"
        )
        self._error_label.show()

    def _on_create(self):
        """Build ComputedColumn definition and compute."""
        name = self._name_edit.text().strip()
        if not name:
            self._show_error("Column name is required.")
            return

        defn = self._build_definition(name)
        if defn is None:
            return

        # Run in worker thread (NFR-3.2)
        self._worker = ComputeWorker(self._parser, defn, self._df, self)
        self._worker.finished.connect(lambda s: self._on_compute_done(defn, s))
        self._worker.error.connect(self._show_error)
        self._worker.progress.connect(self._progress_bar.setValue)
        self._progress_bar.show()
        self._worker.start()

    def _on_compute_done(self, defn: ComputedColumn, series: Optional[pl.Series]):
        self._progress_bar.hide()
        if series is None:
            return  # cancelled
        self._result_series = series
        # Show preview
        preview_vals = series.head(10).to_list()
        self._preview_text.setText(str(preview_vals))
        self.column_created.emit(defn, series)
        self.accept()

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(3000)
        self.reject()

    def _build_definition(self, name: str) -> Optional[ComputedColumn]:
        """Build ComputedColumn from UI state."""
        type_id = self._type_group.checkedId()

        if type_id == 0:  # Formula
            formula = self._formula_edit.text().strip()
            if not formula:
                self._show_error("Formula is required.")
                return None
            try:
                self._parser.validate(formula, self._df)
            except FormulaError as e:
                self._show_error(str(e))
                return None
            refs = self._parser.extract_column_references(formula)
            return ComputedColumn(
                name=name,
                kind="formula",
                expression=formula,
                depends_on=list(refs),
            )

        source = self._source_combo.currentText()
        if not source:
            self._show_error("Select a source column.")
            return None

        if type_id == 1:  # Moving Average
            return ComputedColumn(
                name=name,
                kind="moving_avg",
                expression=source,
                params={"window": self._window_spin.value()},
                depends_on=[source],
            )
        if type_id == 2:  # Difference
            return ComputedColumn(
                name=name,
                kind="difference",
                expression=source,
                params={"order": self._order_spin.value()},
                depends_on=[source],
            )
        if type_id == 3:  # Cumsum
            return ComputedColumn(
                name=name,
                kind="cumsum",
                expression=source,
                depends_on=[source],
            )
        if type_id == 4:  # Normalize
            return ComputedColumn(
                name=name,
                kind="normalize",
                expression=source,
                params={"method": self._norm_combo.currentText()},
                depends_on=[source],
            )

        self._show_error("Unknown type selection.")
        return None

    # ── Public API ────────────────────────────────────────────

    def get_result(self) -> Optional[ComputedColumn]:
        """Return the last built ComputedColumn definition, or None."""
        # This is called after dialog acceptance
        name = self._name_edit.text().strip()
        if name:
            return self._build_definition(name)
        return None
