"""UI import smoke tests.

Goal: catch import-time errors in UI modules (e.g., NameError from type annotations)
without requiring a GUI display.

We intentionally keep this lightweight: import-only, no QApplication creation.
"""

import importlib

import pytest


def _import(module: str) -> None:
    importlib.import_module(module)


# Import smoke coverage:
# - Catch import-time errors in UI modules (e.g., NameError from annotations)
# - Avoid any module that *creates* a QApplication at import time (should not happen)
#
# Keep this list explicit (not auto-discovered) so CI failures are deterministic.
UI_MODULES = [
    # Top-level UI
    "data_graph_studio.ui.main_window",
    "data_graph_studio.ui.theme",
    "data_graph_studio.ui.shortcuts",
    "data_graph_studio.ui.drawing",
    "data_graph_studio.ui.dashboard",
    "data_graph_studio.ui.floatable",
    "data_graph_studio.ui.floating_graph",

    # Views
    "data_graph_studio.ui.views.project_tree_view",

    # Controllers
    "data_graph_studio.ui.controllers.ipc_controller",
    "data_graph_studio.ui.controllers.file_loading_controller",
    "data_graph_studio.ui.controllers.dataset_controller",
    "data_graph_studio.ui.controllers.profile_ui_controller",

    # Toolbars
    "data_graph_studio.ui.toolbars.compare_toolbar",

    # Dialogs
    "data_graph_studio.ui.dialogs.command_palette_dialog",
    "data_graph_studio.ui.dialogs.computed_column_dialog",
    "data_graph_studio.ui.dialogs.export_dialog",
    "data_graph_studio.ui.dialogs.multi_file_dialog",
    "data_graph_studio.ui.dialogs.parsing_preview_dialog",
    "data_graph_studio.ui.dialogs.profile_comparison_dialog",
    "data_graph_studio.ui.dialogs.profile_manager_dialog",
    "data_graph_studio.ui.dialogs.report_dialog",
    "data_graph_studio.ui.dialogs.save_setting_dialog",
    "data_graph_studio.ui.dialogs.shortcut_edit_dialog",
    "data_graph_studio.ui.dialogs.shortcut_help_dialog",
    "data_graph_studio.ui.dialogs.streaming_dialog",

    # Wizards
    "data_graph_studio.ui.wizards.new_project_wizard",
    "data_graph_studio.ui.wizards.parsing_step",
    "data_graph_studio.ui.wizards.graph_setup_step",
    "data_graph_studio.ui.wizards.wpr_convert_step",
    "data_graph_studio.ui.wizards.finish_step",

    # Panels (most frequently touched UI)
    "data_graph_studio.ui.panels.graph_panel",
    "data_graph_studio.ui.panels.graph_options_panel",
    "data_graph_studio.ui.panels.graph_widgets",
    "data_graph_studio.ui.panels.main_graph",
    "data_graph_studio.ui.panels.legend_panel",
    "data_graph_studio.ui.panels.legend_settings_panel",
    "data_graph_studio.ui.panels.stat_panel",
    "data_graph_studio.ui.panels.summary_panel",
    "data_graph_studio.ui.panels.table_panel",
    "data_graph_studio.ui.panels.filter_panel",
    "data_graph_studio.ui.panels.details_panel",
    "data_graph_studio.ui.panels.property_panel",
    "data_graph_studio.ui.panels.dashboard_panel",
    "data_graph_studio.ui.panels.dataset_manager_panel",
    "data_graph_studio.ui.panels.history_panel",
    "data_graph_studio.ui.panels.annotation_panel",
    "data_graph_studio.ui.panels.sliding_window",
    "data_graph_studio.ui.panels.tooltip_config",
    "data_graph_studio.ui.panels.color_scheme",
    "data_graph_studio.ui.panels.empty_state",
    "data_graph_studio.ui.panels.grouped_table_model",
    "data_graph_studio.ui.panels.comparison_stats_panel",
    "data_graph_studio.ui.panels.overlay_stats_widget",
    "data_graph_studio.ui.panels.profile_bar",
    "data_graph_studio.ui.panels.profile_overlay",
    "data_graph_studio.ui.panels.profile_difference",
    "data_graph_studio.ui.panels.profile_side_by_side",
    "data_graph_studio.ui.panels.side_by_side_layout",
    "data_graph_studio.ui.panels.mini_graph_widget",
    "data_graph_studio.ui.panels.data_tab",

    # UI models
    "data_graph_studio.ui.models.profile_model",
    "data_graph_studio.ui.models.undo_history_model",
]


@pytest.mark.parametrize("module", UI_MODULES)
def test_ui_import_smoke(module: str) -> None:
    _import(module)
