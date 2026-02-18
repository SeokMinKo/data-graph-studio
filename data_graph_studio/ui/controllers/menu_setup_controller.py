"""MenuSetupController - extracted from MainWindow."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtGui import QAction, QKeySequence

from ...core.state import ChartType
from ...core.export_controller import ExportFormat

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    from ..main_window import MainWindow

class MenuSetupController:
    """Controller extracted from MainWindow."""

    def __init__(self, main_window: 'MainWindow'):
        self.w = main_window

    def _setup_menubar(self):
        """메뉴바 설정 - 새 구조"""
        menubar = self.w.menuBar()
        # Style handled by global theme stylesheet

        # ============================================================
        # File Menu
        # ============================================================
        file_menu = menubar.addMenu("&File")

        # Open Data (with wizard)
        open_data_action = QAction("Open &Data...", self.w)
        open_data_action.setShortcut(QKeySequence.Open)
        open_data_action.setStatusTip("Open data file with New Project Wizard (Ctrl+O)")
        open_data_action.triggered.connect(self.w._on_open_file)
        file_menu.addAction(open_data_action)

        # Open Data Without Wizard
        open_no_wizard_action = QAction("Open Without &Wizard...", self.w)
        open_no_wizard_action.setShortcut("Ctrl+Shift+O")
        open_no_wizard_action.setStatusTip("Open data file without wizard - quick mode (Ctrl+Shift+O)")
        open_no_wizard_action.triggered.connect(self.w._on_open_file_without_wizard)
        file_menu.addAction(open_no_wizard_action)

        # Open Profile
        open_profile_action = QAction("Open &Profile...", self.w)
        open_profile_action.setShortcut("Ctrl+Alt+O")
        open_profile_action.setStatusTip("Load a saved profile file (Ctrl+Alt+O)")
        open_profile_action.triggered.connect(self.w._on_open_profile)
        file_menu.addAction(open_profile_action)

        # Open Project
        open_project_action = QAction("Open Pro&ject...", self.w)
        open_project_action.setShortcut("Ctrl+Alt+P")
        open_project_action.setStatusTip("Load a DGS project file (Ctrl+Alt+P)")
        open_project_action.triggered.connect(self.w._on_open_project)
        file_menu.addAction(open_project_action)

        file_menu.addSeparator()

        # Save Data
        save_data_action = QAction("Save Data", self.w)
        save_data_action.setShortcut(QKeySequence.Save)
        save_data_action.setStatusTip("Save current data (Ctrl+S)")
        save_data_action.triggered.connect(self.w._on_save_data)
        file_menu.addAction(save_data_action)

        # Save Data As
        save_data_as_action = QAction("Save Data As...", self.w)
        save_data_as_action.setShortcut("Ctrl+Shift+S")
        save_data_as_action.setStatusTip("Save current data to a new file")
        save_data_as_action.triggered.connect(self.w._on_save_data_as)
        file_menu.addAction(save_data_as_action)

        # Save Profile
        save_profile_action = QAction("Save Profile", self.w)
        save_profile_action.setStatusTip("Save active profile to last path")
        save_profile_action.triggered.connect(self.w._on_save_profile_file)
        file_menu.addAction(save_profile_action)

        # Save Profile As
        save_profile_as_action = QAction("Save Profile As...", self.w)
        save_profile_as_action.setStatusTip("Save active profile to a new file")
        save_profile_as_action.triggered.connect(self.w._on_save_profile_file_as)
        file_menu.addAction(save_profile_as_action)

        # Save Project
        save_project_action = QAction("Save Project", self.w)
        save_project_action.setShortcut("Ctrl+Alt+S")
        save_project_action.setStatusTip("Save project with profiles (Ctrl+Alt+S)")
        save_project_action.triggered.connect(self.w._on_save_project_file)
        file_menu.addAction(save_project_action)

        # Save Project As
        save_project_as_action = QAction("Save Project As...", self.w)
        save_project_as_action.setStatusTip("Save project with profiles to a new file")
        save_project_as_action.triggered.connect(self.w._on_save_project_file_as)
        file_menu.addAction(save_project_as_action)

        file_menu.addSeparator()

        # Save Profile Bundle As
        save_bundle_as_action = QAction("Save Profile Bundle As...", self.w)
        save_bundle_as_action.setStatusTip("Save all profiles as a bundle file")
        save_bundle_as_action.triggered.connect(self.w._on_save_profile_bundle_as)
        file_menu.addAction(save_bundle_as_action)

        file_menu.addSeparator()

        # Export submenu
        export_menu = file_menu.addMenu("&Export")

        # Export Image (PNG/SVG)
        self.w._export_image_png_action = QAction("Image (PNG)...", self.w)
        self.w._export_image_png_action.setStatusTip("Export chart as PNG image")
        self.w._export_image_png_action.triggered.connect(lambda: self.w._on_export_image(ExportFormat.PNG))
        export_menu.addAction(self.w._export_image_png_action)

        self.w._export_image_svg_action = QAction("Image (SVG)...", self.w)
        self.w._export_image_svg_action.setStatusTip("Export chart as SVG image")
        self.w._export_image_svg_action.triggered.connect(lambda: self.w._on_export_image(ExportFormat.SVG))
        export_menu.addAction(self.w._export_image_svg_action)

        export_menu.addSeparator()

        # Export Data
        self.w._export_data_csv_action = QAction("Data (CSV)...", self.w)
        self.w._export_data_csv_action.setStatusTip("Export data as CSV")
        self.w._export_data_csv_action.triggered.connect(lambda: self.w._on_export_data(ExportFormat.CSV))
        export_menu.addAction(self.w._export_data_csv_action)

        self.w._export_data_excel_action = QAction("Data (Excel)...", self.w)
        self.w._export_data_excel_action.setStatusTip("Export data as Excel")
        self.w._export_data_excel_action.triggered.connect(lambda: self.w._on_export_data(ExportFormat.EXCEL))
        export_menu.addAction(self.w._export_data_excel_action)

        self.w._export_data_parquet_action = QAction("Data (Parquet)...", self.w)
        self.w._export_data_parquet_action.setStatusTip("Export data as Parquet")
        self.w._export_data_parquet_action.triggered.connect(lambda: self.w._on_export_data(ExportFormat.PARQUET))
        export_menu.addAction(self.w._export_data_parquet_action)

        export_menu.addSeparator()

        # Export Report
        self.w._export_report_html_action = QAction("Report (HTML)...", self.w)
        self.w._export_report_html_action.setStatusTip("Export report as HTML")
        self.w._export_report_html_action.triggered.connect(self.w._on_export_report)
        export_menu.addAction(self.w._export_report_html_action)

        self.w._export_report_pptx_action = QAction("Report (PPTX)...", self.w)
        self.w._export_report_pptx_action.setStatusTip("Export report as PowerPoint")
        self.w._export_report_pptx_action.triggered.connect(self.w._on_export_report)
        export_menu.addAction(self.w._export_report_pptx_action)

        export_menu.addSeparator()

        # Quick Export (Ctrl+E)
        self.w._export_quick_action = QAction("Export...", self.w)
        self.w._export_quick_action.setShortcut("Ctrl+E")
        self.w._export_quick_action.setStatusTip("Open export dialog (Ctrl+E)")
        self.w._export_quick_action.triggered.connect(self.w._on_export_dialog)
        export_menu.addAction(self.w._export_quick_action)

        # Keep legacy report action for backward compat
        export_report_action = QAction("Export &Report (Legacy)...", self.w)
        export_report_action.setShortcut("Ctrl+R")
        export_report_action.setStatusTip("Export data and charts as a report")
        export_report_action.triggered.connect(self.w._on_export_report)
        file_menu.addAction(export_report_action)

        # Import
        import_action = QAction("&Import...", self.w)
        import_action.setShortcut("Ctrl+I")
        import_action.setStatusTip("Import data from various sources")
        import_action.triggered.connect(self.w._on_import_data)
        file_menu.addAction(import_action)

        file_menu.addSeparator()

        # Watch for Changes
        self.w._watch_file_action = QAction("Watch for Changes", self.w)
        self.w._watch_file_action.setCheckable(True)
        self.w._watch_file_action.setChecked(False)
        self.w._watch_file_action.setStatusTip("Auto-reload when the source file changes on disk")
        self.w._watch_file_action.triggered.connect(self.w._file_controller._toggle_file_watch)
        file_menu.addAction(self.w._watch_file_action)

        file_menu.addSeparator()

        # Recent Files submenu
        self.w._recent_files_menu = file_menu.addMenu("Recent Files")
        self.w._recent_files_menu.setStatusTip("Recently opened files")
        self.w._update_recent_files_menu()

        file_menu.addSeparator()

        # Exit
        exit_action = QAction("E&xit", self.w)
        exit_action.setShortcut(QKeySequence.Quit)
        exit_action.setStatusTip("Exit application (Ctrl+Q)")
        exit_action.triggered.connect(self.w.close)
        file_menu.addAction(exit_action)

        # ============================================================
        # Edit Menu
        # ============================================================
        edit_menu = menubar.addMenu("&Edit")

        undo_action = QAction("&Undo", self.w)
        undo_action.setShortcut(QKeySequence.Undo)
        undo_action.setStatusTip("Undo last action (Ctrl+Z)")
        undo_action.triggered.connect(self.w._on_undo)
        edit_menu.addAction(undo_action)

        redo_action = QAction("&Redo", self.w)
        redo_action.setShortcut(QKeySequence("Ctrl+Y"))
        redo_action.setStatusTip("Redo last undone action (Ctrl+Y)")
        redo_action.triggered.connect(self.w._on_redo)
        edit_menu.addAction(redo_action)

        edit_menu.addSeparator()

        copy_action = QAction("&Copy", self.w)
        copy_action.setShortcut(QKeySequence.Copy)
        copy_action.setStatusTip("Copy selection (Ctrl+C)")
        copy_action.triggered.connect(self.w._on_copy_selection)
        edit_menu.addAction(copy_action)

        paste_action = QAction("&Paste", self.w)
        paste_action.setShortcut(QKeySequence.Paste)
        paste_action.setStatusTip("Paste from clipboard (Ctrl+V)")
        paste_action.triggered.connect(self.w._paste_from_clipboard)
        edit_menu.addAction(paste_action)

        edit_menu.addSeparator()

        find_action = QAction("&Find...", self.w)
        find_action.setShortcut(QKeySequence.Find)
        find_action.setStatusTip("Find data (Ctrl+F)")
        find_action.triggered.connect(self.w._on_find_data)
        edit_menu.addAction(find_action)

        goto_row_action = QAction("&Go to Row...", self.w)
        goto_row_action.setShortcut(QKeySequence("Ctrl+G"))
        goto_row_action.setStatusTip("Go to specific row (Ctrl+G)")
        goto_row_action.triggered.connect(self.w._on_goto_row)
        edit_menu.addAction(goto_row_action)

        select_all_action = QAction("Select &All", self.w)
        select_all_action.setShortcut(QKeySequence.SelectAll)
        select_all_action.setStatusTip("Select all data (Ctrl+A)")
        select_all_action.triggered.connect(self.w._on_select_all)
        edit_menu.addAction(select_all_action)

        # ============================================================
        # View Menu
        # ============================================================
        view_menu = menubar.addMenu("&View")

        # View actions dict (for settings apply compatibility)
        self.w._view_actions = {}

        # Graph Elements submenu
        graph_elements_menu = view_menu.addMenu("&Graph Elements")
        
        self.w._graph_element_actions = {}
        
        float_graph_action = QAction("Float Graph Panel", self.w)
        float_graph_action.setStatusTip("Float the graph panel into a separate window")
        float_graph_action.triggered.connect(lambda: self.w._float_main_panel("graph"))
        graph_elements_menu.addAction(float_graph_action)
        graph_elements_menu.addSeparator()
        
        legend_action = QAction("Legend", self.w)
        legend_action.setToolTip("Toggle chart legend visibility")
        legend_action.setCheckable(True)
        legend_action.setChecked(True)
        legend_action.triggered.connect(self.w._on_toggle_legend)
        graph_elements_menu.addAction(legend_action)
        self.w._graph_element_actions["legend"] = legend_action
        self.w._show_legend_action = legend_action
        
        grid_action = QAction("Grid", self.w)
        grid_action.setToolTip("Toggle chart grid lines")
        grid_action.setCheckable(True)
        grid_action.setChecked(True)
        grid_action.triggered.connect(self.w._on_toggle_grid)
        graph_elements_menu.addAction(grid_action)
        self.w._graph_element_actions["grid"] = grid_action
        self.w._show_grid_action = grid_action
        
        statistics_overlay_action = QAction("Statistics Overlay", self.w)
        statistics_overlay_action.setToolTip("Show statistics overlay on chart")
        statistics_overlay_action.setCheckable(True)
        statistics_overlay_action.setChecked(False)
        statistics_overlay_action.triggered.connect(self.w._on_toggle_statistics_overlay)
        graph_elements_menu.addAction(statistics_overlay_action)
        self.w._graph_element_actions["statistics_overlay"] = statistics_overlay_action
        
        axis_labels_action = QAction("Axis Labels", self.w)
        axis_labels_action.setToolTip("Toggle axis labels on chart")
        axis_labels_action.setCheckable(True)
        axis_labels_action.setChecked(True)
        axis_labels_action.triggered.connect(self.w._on_toggle_axis_labels)
        graph_elements_menu.addAction(axis_labels_action)
        self.w._graph_element_actions["axis_labels"] = axis_labels_action

        graph_elements_menu.addSeparator()
        drawing_style_action = QAction("Drawing Style...", self.w)
        drawing_style_action.setToolTip("Configure drawing tool style")
        drawing_style_action.triggered.connect(self.w._on_drawing_style)
        graph_elements_menu.addAction(drawing_style_action)

        delete_drawing_action = QAction("Delete Selected Drawing", self.w)
        delete_drawing_action.setToolTip("Delete the currently selected drawing (Delete)")
        # Shortcut handled in keyPressEvent to avoid text input conflicts
        delete_drawing_action.triggered.connect(self.w._on_delete_drawing)
        graph_elements_menu.addAction(delete_drawing_action)
        self.w._delete_drawing_action = delete_drawing_action

        clear_drawings_action = QAction("Clear All Drawings", self.w)
        clear_drawings_action.setToolTip("Remove all drawings from the chart")
        clear_drawings_action.triggered.connect(self.w._on_clear_drawings)
        graph_elements_menu.addAction(clear_drawings_action)

        # Table Elements submenu
        table_elements_menu = view_menu.addMenu("&Table Elements")
        
        self.w._table_element_actions = {}
        
        float_table_action = QAction("Float Table Panel", self.w)
        float_table_action.setStatusTip("Float the table panel into a separate window")
        float_table_action.triggered.connect(lambda: self.w._float_main_panel("table"))
        table_elements_menu.addAction(float_table_action)
        table_elements_menu.addSeparator()
        
        row_numbers_action = QAction("Row Numbers", self.w)
        row_numbers_action.setToolTip("Show or hide row numbers in table")
        row_numbers_action.setCheckable(True)
        row_numbers_action.setChecked(True)
        row_numbers_action.triggered.connect(self.w._on_toggle_row_numbers)
        table_elements_menu.addAction(row_numbers_action)
        self.w._table_element_actions["row_numbers"] = row_numbers_action
        
        column_headers_action = QAction("Column Headers", self.w)
        column_headers_action.setToolTip("Show or hide column headers in table")
        column_headers_action.setCheckable(True)
        column_headers_action.setChecked(True)
        column_headers_action.triggered.connect(self.w._on_toggle_column_headers)
        table_elements_menu.addAction(column_headers_action)
        self.w._table_element_actions["column_headers"] = column_headers_action
        
        filter_bar_action = QAction("Filter Bar", self.w)
        filter_bar_action.setToolTip("Show or hide table filter bar")
        filter_bar_action.setCheckable(True)
        filter_bar_action.setChecked(False)
        filter_bar_action.triggered.connect(self.w._on_toggle_filter_bar)
        table_elements_menu.addAction(filter_bar_action)
        self.w._table_element_actions["filter_bar"] = filter_bar_action

        view_menu.addSeparator()

        # Multi-Grid View
        multi_grid_action = QAction("&Multi-Grid View", self.w)
        multi_grid_action.setShortcut("Ctrl+M")
        multi_grid_action.setStatusTip("Display multiple graphs in a grid layout")
        multi_grid_action.triggered.connect(self.w._on_multi_grid_view)
        view_menu.addAction(multi_grid_action)

        view_menu.addSeparator()

        # ===== v2 Feature Menu Items =====

        # Feature 1: Dashboard Mode
        self.w._dashboard_mode_action = QAction("&Dashboard Mode", self.w)
        self.w._dashboard_mode_action.setShortcut("Ctrl+D")
        self.w._dashboard_mode_action.setStatusTip("Toggle dashboard mode with multiple chart cells (Ctrl+D)")
        self.w._dashboard_mode_action.setCheckable(True)
        self.w._dashboard_mode_action.triggered.connect(self.w._on_toggle_dashboard_mode)
        view_menu.addAction(self.w._dashboard_mode_action)

        # Feature 5: Annotation Panel
        self.w._annotation_panel_action = QAction("&Annotations Panel", self.w)
        self.w._annotation_panel_action.setShortcut("Ctrl+Shift+A")
        self.w._annotation_panel_action.setStatusTip("Toggle annotations side panel (Ctrl+Shift+A)")
        self.w._annotation_panel_action.setCheckable(True)
        self.w._annotation_panel_action.triggered.connect(self.w._on_toggle_annotation_panel)
        view_menu.addAction(self.w._annotation_panel_action)

        # Add Annotation
        self.w._add_annotation_action = QAction("Add A&nnotation", self.w)
        self.w._add_annotation_action.setShortcut("Ctrl+Shift+N")
        self.w._add_annotation_action.setStatusTip("Add a new annotation to the chart (Ctrl+Shift+N)")
        self.w._add_annotation_action.triggered.connect(self.w._on_add_annotation)
        view_menu.addAction(self.w._add_annotation_action)

        view_menu.addSeparator()

        # Theme submenu
        theme_menu = view_menu.addMenu("&Theme")
        self.w._theme_actions = {}

        light_theme_action = QAction("Light", self.w)
        light_theme_action.setToolTip("Switch to light theme")
        light_theme_action.setCheckable(True)
        light_theme_action.setChecked(False)
        light_theme_action.triggered.connect(lambda: self.w._on_theme_changed("light"))
        theme_menu.addAction(light_theme_action)
        self.w._theme_actions["light"] = light_theme_action

        dark_theme_action = QAction("Dark", self.w)
        dark_theme_action.setToolTip("Switch to dark theme")
        dark_theme_action.setCheckable(True)
        dark_theme_action.triggered.connect(lambda: self.w._on_theme_changed("dark"))
        theme_menu.addAction(dark_theme_action)
        self.w._theme_actions["dark"] = dark_theme_action

        midnight_theme_action = QAction("Midnight", self.w)
        midnight_theme_action.setToolTip("Switch to midnight theme")
        midnight_theme_action.setCheckable(True)
        midnight_theme_action.setChecked(True)
        midnight_theme_action.triggered.connect(lambda: self.w._on_theme_changed("midnight"))
        theme_menu.addAction(midnight_theme_action)
        self.w._theme_actions["midnight"] = midnight_theme_action

        theme_menu.addSeparator()

        # Cycle theme shortcut
        cycle_theme_action = QAction("Cycle Theme", self.w)
        cycle_theme_action.setShortcut("Ctrl+T")
        cycle_theme_action.setStatusTip("Cycle through themes (Ctrl+T)")
        cycle_theme_action.triggered.connect(self.w._on_cycle_theme)
        theme_menu.addAction(cycle_theme_action)

        view_menu.addSeparator()

        # Streaming menu items
        self.w._start_streaming_action = QAction("Start &Streaming...", self.w)
        self.w._start_streaming_action.setStatusTip("Open streaming configuration dialog")
        self.w._start_streaming_action.triggered.connect(self.w._on_start_streaming_dialog)
        view_menu.addAction(self.w._start_streaming_action)

        self.w._stop_streaming_action = QAction("Sto&p Streaming", self.w)
        self.w._stop_streaming_action.setStatusTip("Stop the active streaming session")
        self.w._stop_streaming_action.setEnabled(False)
        self.w._stop_streaming_action.triggered.connect(self.w._on_stop_streaming)
        view_menu.addAction(self.w._stop_streaming_action)

        # ============================================================
        # Data Menu
        # ============================================================
        data_menu = menubar.addMenu("&Data")

        # Add Calculated Field
        self.w._add_calc_field_action = QAction("&Add Calculated Field...", self.w)
        self.w._add_calc_field_action.setShortcut("Ctrl+Alt+F")
        self.w._add_calc_field_action.setStatusTip("Add a new calculated column based on expression")
        self.w._add_calc_field_action.triggered.connect(self.w._on_add_calculated_field)
        data_menu.addAction(self.w._add_calc_field_action)

        # Remove Field
        self.w._remove_field_action = QAction("&Remove Field...", self.w)
        self.w._remove_field_action.setStatusTip("Remove a field/column from the data")
        self.w._remove_field_action.triggered.connect(self.w._on_remove_field)
        data_menu.addAction(self.w._remove_field_action)

        data_menu.addSeparator()

        # Sort
        self.w._sort_data_action = QAction("&Sort...", self.w)
        self.w._sort_data_action.setStatusTip("Sort data by column")
        self.w._sort_data_action.triggered.connect(self.w._on_sort_data)
        data_menu.addAction(self.w._sort_data_action)

        # Filter
        self.w._filter_data_action = QAction("&Filter Data", self.w)
        self.w._filter_data_action.setStatusTip("Toggle data filter")
        self.w._filter_data_action.triggered.connect(self.w._on_filter_data)
        data_menu.addAction(self.w._filter_data_action)

        data_menu.addSeparator()

        # Remove Duplicates
        self.w._remove_duplicates_action = QAction("Remove &Duplicates", self.w)
        self.w._remove_duplicates_action.setStatusTip("Remove duplicate rows")
        self.w._remove_duplicates_action.triggered.connect(self.w._on_remove_duplicates)
        data_menu.addAction(self.w._remove_duplicates_action)

        # Data Summary
        self.w._data_summary_action = QAction("Data Su&mmary...", self.w)
        self.w._data_summary_action.setStatusTip("Show data summary statistics")
        self.w._data_summary_action.triggered.connect(self.w._on_data_summary)
        data_menu.addAction(self.w._data_summary_action)

        # ============================================================
        # Logger Menu
        # ============================================================
        logger_menu = menubar.addMenu("&Logger")

        start_trace_action = QAction("&Start Trace...", self.w)
        start_trace_action.setStatusTip("Start block layer tracing (uses saved config or opens Configure)")
        start_trace_action.triggered.connect(self.w._on_start_trace)
        logger_menu.addAction(start_trace_action)

        logger_menu.addSeparator()

        compare_traces_action = QAction("Compare &Traces...", self.w)
        compare_traces_action.setStatusTip("Compare two ftrace files (before/after)")
        compare_traces_action.triggered.connect(self.w._on_compare_traces)
        logger_menu.addAction(compare_traces_action)

        logger_menu.addSeparator()

        configure_action = QAction("&Configure...", self.w)
        configure_action.setStatusTip("Open the Trace Configuration dialog")
        configure_action.triggered.connect(self.w._on_configure_trace)
        logger_menu.addAction(configure_action)

        # ============================================================
        # Parser Menu
        # ============================================================
        parser_menu = menubar.addMenu("&Parser")

        ftrace_action = QAction("&Ftrace Parser...", self.w)
        ftrace_action.setStatusTip("Parse ftrace log file and load into table")
        ftrace_action.triggered.connect(lambda: self.w._on_run_parser("ftrace"))
        parser_menu.addAction(ftrace_action)

        parser_menu.addSeparator()

        manage_profiles_action = QAction("Manage &Profiles...", self.w)
        manage_profiles_action.setStatusTip("Manage parser profiles")
        manage_profiles_action.triggered.connect(self.w._on_manage_parser_profiles)
        parser_menu.addAction(manage_profiles_action)

        parser_menu.addSeparator()

        # Loading profiles
        save_loading_profile_action = QAction("Save Loading Profile...", self.w)
        save_loading_profile_action.setStatusTip("Save current parsing settings as a reusable profile")
        save_loading_profile_action.triggered.connect(self.w._file_controller._save_loading_profile)
        parser_menu.addAction(save_loading_profile_action)

        load_loading_profile_action = QAction("Load Profile...", self.w)
        load_loading_profile_action.setStatusTip("Load saved parsing settings profile")
        load_loading_profile_action.triggered.connect(self.w._file_controller._load_loading_profile)
        parser_menu.addAction(load_loading_profile_action)

        # ============================================================
        # Graph Menu
        # ============================================================
        graph_menu = menubar.addMenu("&Graph")

        # Statistics submenu
        statistics_menu = graph_menu.addMenu("&Statistics")

        histogram_bins_action = QAction("&Histogram Bins...", self.w)
        histogram_bins_action.setStatusTip("Set the number of bins for histograms")
        histogram_bins_action.triggered.connect(self.w._on_set_both_bins)
        statistics_menu.addAction(histogram_bins_action)

        # Options submenu
        options_menu = graph_menu.addMenu("&Options")

        # Chart Type submenu within Options (with shortcut hints)
        chart_type_menu = options_menu.addMenu("Chart &Type")
        _chart_shortcuts = {
            ChartType.LINE: "1", ChartType.BAR: "2", ChartType.SCATTER: "3",
            ChartType.AREA: "5",
        }
        for chart_type in ChartType:
            shortcut_hint = _chart_shortcuts.get(chart_type, "")
            label = chart_type.value.title()
            if shortcut_hint:
                label = f"{label} ({shortcut_hint})"
            action = QAction(label, self.w)
            action.triggered.connect(lambda checked, ct=chart_type: self.w.state.set_chart_type(ct))
            chart_type_menu.addAction(action)

        options_menu.addSeparator()

        # Axis settings
        axis_settings_action = QAction("&Axis Settings...", self.w)
        axis_settings_action.setStatusTip("Configure axis range, labels, and scale")
        axis_settings_action.triggered.connect(self.w._on_axis_settings)
        options_menu.addAction(axis_settings_action)

        # Curve fitting
        curve_fitting_action = QAction("&Curve Fitting...", self.w)
        curve_fitting_action.setStatusTip("Configure curve fitting options")
        curve_fitting_action.triggered.connect(self.w._on_curve_fitting)
        options_menu.addAction(curve_fitting_action)

        # Trend line
        self.w._trend_line_action = QAction("Add &Trend Line...", self.w)
        self.w._trend_line_action.setStatusTip("Add a trend line to the current graph")
        self.w._trend_line_action.triggered.connect(self.w._on_add_trend_line)
        options_menu.addAction(self.w._trend_line_action)

        # ============================================================
        # Help Menu
        # ============================================================
        help_menu = menubar.addMenu("&Help")

        search_features_action = QAction("&Search Features...", self.w)
        search_features_action.setShortcut("Ctrl+Shift+P")
        search_features_action.setStatusTip("Open Command Palette to search and execute features (Ctrl+Shift+P)")
        search_features_action.triggered.connect(self.w._on_open_command_palette)
        help_menu.addAction(search_features_action)

        # Also bind F1 as alternative shortcut
        search_features_f1_action = QAction("Search Features (F1)", self.w)
        search_features_f1_action.setShortcut("F1")
        search_features_f1_action.triggered.connect(self.w._on_open_command_palette)
        self.w.addAction(search_features_f1_action)  # Window-level shortcut

        help_menu.addSeparator()

        shortcuts_action = QAction("&Keyboard Shortcuts...", self.w)
        shortcuts_action.setShortcut("Ctrl+/")
        shortcuts_action.setStatusTip("Show keyboard shortcuts reference")
        shortcuts_action.triggered.connect(self.w._show_shortcuts_dialog)
        help_menu.addAction(shortcuts_action)

        edit_shortcuts_action = QAction("&Customize Shortcuts...", self.w)
        edit_shortcuts_action.setStatusTip("Customize keyboard shortcuts")
        edit_shortcuts_action.triggered.connect(self.w._show_edit_shortcuts_dialog)
        help_menu.addAction(edit_shortcuts_action)

        help_menu.addSeparator()

        check_updates_action = QAction("Check for &Updates...", self.w)
        check_updates_action.setStatusTip("Check GitHub Releases and update (Windows)")
        check_updates_action.triggered.connect(lambda: self.w._auto_check_updates(force_ui=True))
        help_menu.addAction(check_updates_action)

        about_action = QAction("&About", self.w)
        about_action.setStatusTip("About Data Graph Studio")
        about_action.triggered.connect(self.w._show_about)
        help_menu.addAction(about_action)


    def _update_recent_files_menu(self):
        """최근 파일 메뉴 업데이트 — delegates to FileLoadingController"""
        self.w._file_controller._update_recent_files_menu()


    def _update_menu_state(self):
        """Enable/disable Data and Graph menu items based on data state."""
        has_data = self.w.state.is_data_loaded

        # Data menu items
        for action in (
            self.w._add_calc_field_action,
            self.w._remove_field_action,
            self.w._sort_data_action,
            self.w._filter_data_action,
            self.w._remove_duplicates_action,
            self.w._data_summary_action,
        ):
            action.setEnabled(has_data)

        # Graph menu items
        if hasattr(self.w, '_trend_line_action'):
            self.w._trend_line_action.setEnabled(has_data)

    def _update_export_menu_state(self):
        """Enable/disable export menu items based on data/graph state"""
        has_data = self.w.state.is_data_loaded
        has_graph = has_data and (bool(self.w.state.value_columns) or bool(self.w.state.x_column))

        # Image export requires a graph
        for action in (self.w._export_image_png_action, self.w._export_image_svg_action):
            action.setEnabled(has_graph)

        # Data export requires data
        for action in (self.w._export_data_csv_action, self.w._export_data_excel_action,
                       self.w._export_data_parquet_action):
            action.setEnabled(has_data)

        # Report export requires data
        for action in (self.w._export_report_html_action, self.w._export_report_pptx_action):
            action.setEnabled(has_data)

        # Quick export
        self.w._export_quick_action.setEnabled(has_data)


