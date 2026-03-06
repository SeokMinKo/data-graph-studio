"""Converter Options Panel — editable converter parameters with debounced re-computation."""

from __future__ import annotations

from typing import Any, Dict

from PySide6.QtCore import Signal, QTimer
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QFormLayout,
    QGroupBox,
    QSpinBox,
    QDoubleSpinBox,
    QLineEdit,
    QPushButton,
    QLabel,
)


class ConverterOptionsPanel(QWidget):
    """Panel for editing converter-specific options."""

    options_changed = Signal(dict)  # emitted after debounce with full options dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets: Dict[str, QWidget] = {}
        self._option_defs: list = []
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.setInterval(300)
        self._debounce_timer.timeout.connect(self._emit_options)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        self._info_label = QLabel("No converter active")
        layout.addWidget(self._info_label)
        self._form_group = QGroupBox("Converter Options")
        self._form_layout = QFormLayout(self._form_group)
        layout.addWidget(self._form_group)
        self._form_group.hide()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_defaults)
        layout.addWidget(reset_btn)
        layout.addStretch()

    def set_converter(self, converter: str):
        """Configure panel for given converter type."""
        from data_graph_studio.parsers.ftrace_parser import FtraceParser

        self._option_defs = FtraceParser.get_option_defs(converter)

        # Clear old widgets
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._widgets.clear()

        if not self._option_defs:
            self._info_label.setText(f"No options for '{converter}'")
            self._form_group.hide()
            return

        self._info_label.setText(f"Converter: {converter}")
        self._form_group.show()

        for opt in self._option_defs:
            widget = self._create_widget(opt)
            self._widgets[opt["key"]] = widget
            label = QLabel(opt["label"])
            label.setToolTip(opt["description"])
            widget.setToolTip(f"{opt['description']}\nDefault: {opt['default']}")
            self._form_layout.addRow(label, widget)

    def _create_widget(self, opt: dict) -> QWidget:
        if opt["type"] == "int":
            w = QSpinBox()
            w.setRange(0, 99999)
            w.setValue(opt["default"])
            w.valueChanged.connect(self._on_value_changed)
            return w
        elif opt["type"] == "float":
            w = QDoubleSpinBox()
            w.setRange(0.0, 99999.0)
            w.setDecimals(2)
            w.setSingleStep(0.1)
            w.setValue(opt["default"])
            w.valueChanged.connect(self._on_value_changed)
            return w
        else:  # str
            w = QLineEdit()
            w.setText(str(opt["default"]))
            w.setPlaceholderText(f"Default: {opt['default']}")
            w.textChanged.connect(self._on_value_changed)
            return w

    def _on_value_changed(self, *args):
        self._debounce_timer.start()

    def _emit_options(self):
        self.options_changed.emit(self.get_options())

    def get_options(self) -> Dict[str, Any]:
        result = {}
        for opt in self._option_defs:
            w = self._widgets.get(opt["key"])
            if w is None:
                continue
            if opt["type"] == "int":
                result[opt["key"]] = w.value()
            elif opt["type"] == "float":
                result[opt["key"]] = w.value()
            else:
                result[opt["key"]] = w.text()
        return result

    def _reset_defaults(self):
        for opt in self._option_defs:
            w = self._widgets.get(opt["key"])
            if w is None:
                continue
            if opt["type"] == "int":
                w.setValue(opt["default"])
            elif opt["type"] == "float":
                w.setValue(opt["default"])
            else:
                w.setText(str(opt["default"]))
