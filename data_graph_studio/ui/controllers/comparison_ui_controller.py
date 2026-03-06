"""ComparisonUIController - extracted from MainWindow."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, List

from PySide6.QtWidgets import QWidget

from ...core.state import ComparisonMode

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow


class ComparisonUIController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: "MainWindow"):
        self.w = main_window

    def _set_comparison_mode(self, mode: ComparisonMode):
        self.w._dataset_controller._set_comparison_mode(mode)

    def _update_comparison_mode_actions(self, mode: ComparisonMode):
        self.w._dataset_controller._update_comparison_mode_actions(mode)

    def _on_comparison_mode_changed(self, mode_value: str):
        self.w._dataset_controller._on_comparison_mode_changed(mode_value)

    def _on_comparison_started(self, dataset_ids: List[str]):
        self.w._dataset_controller._on_comparison_started(dataset_ids)

    def _start_overlay_comparison(self, dataset_ids: List[str]):
        self.w._dataset_controller._start_overlay_comparison(dataset_ids)

    def _show_overlay_stats_widget(self):
        self.w._dataset_controller._show_overlay_stats_widget()

    def _hide_overlay_stats_widget(self):
        self.w._dataset_controller._hide_overlay_stats_widget()

    def _show_comparison_stats_panel(self):
        self.w._dataset_controller._show_comparison_stats_panel()

    def _on_export_comparison_report(self):
        self.w._dataset_controller._on_export_comparison_report()

    def _start_side_by_side_comparison(self, dataset_ids: List[str]):
        self.w._dataset_controller._start_side_by_side_comparison(dataset_ids)

    def _start_difference_analysis(self, dataset_ids: List[str]):
        self.w._dataset_controller._start_difference_analysis(dataset_ids)

    def _show_comparison_view(self, view_widget: QWidget):
        self.w._dataset_controller._show_comparison_view(view_widget)

    def _remove_comparison_view(self):
        self.w._dataset_controller._remove_comparison_view()

    def _restore_single_view(self):
        self.w._dataset_controller._restore_single_view()

    # ==================== Profile Comparison Views ====================

    def _on_profile_comparison_started(self, mode_value: str, profile_ids: list):
        self.w._dataset_controller._on_profile_comparison_started(
            mode_value, profile_ids
        )

    def _on_profile_comparison_ended(self):
        self.w._dataset_controller._on_profile_comparison_ended()

    # ==================== Streaming ====================
