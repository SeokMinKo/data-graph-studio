"""IPC handler stubs for MainWindow.

All methods here are wired in _setup_ipc_server() and forward
to the appropriate controllers. No logic lives here.
"""


class _MainWindowIpcMixin:
    """Mixin providing IPC command handler stubs for MainWindow.

    Requires: self._ipc_controller (IPCController) set by MainWindow.__init__
    """

    def _ipc_get_state(self, *a, **kw):
        return self._ipc_controller._ipc_get_state(*a, **kw)

    def _ipc_get_data_info(self, *a, **kw):
        return self._ipc_controller._ipc_get_data_info(*a, **kw)

    def _ipc_set_chart_type(self, *a, **kw):
        return self._ipc_controller._ipc_set_chart_type(*a, **kw)

    def _ipc_set_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_columns(*a, **kw)

    def _ipc_load_file(self, *a, **kw):
        return self._ipc_controller._ipc_load_file(*a, **kw)

    def _ipc_get_panels(self, *a, **kw):
        return self._ipc_controller._ipc_get_panels(*a, **kw)

    def _ipc_get_summary(self, *a, **kw):
        return self._ipc_controller._ipc_get_summary(*a, **kw)

    def _ipc_execute(self, *a, **kw):
        return self._ipc_controller._ipc_execute(*a, **kw)

    def _ipc_set_x_column(self, *a, **kw):
        return self._ipc_controller._ipc_set_x_column(*a, **kw)

    def _ipc_set_value_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_value_columns(*a, **kw)

    def _ipc_set_group_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_group_columns(*a, **kw)

    def _ipc_set_hover_columns(self, *a, **kw):
        return self._ipc_controller._ipc_set_hover_columns(*a, **kw)

    def _ipc_clear_all_zones(self, *a, **kw):
        return self._ipc_controller._ipc_clear_all_zones(*a, **kw)

    def _ipc_get_zones(self, *a, **kw):
        return self._ipc_controller._ipc_get_zones(*a, **kw)

    def _ipc_set_theme(self, *a, **kw):
        return self._ipc_controller._ipc_set_theme(*a, **kw)

    def _ipc_refresh(self, *a, **kw):
        return self._ipc_controller._ipc_refresh(*a, **kw)

    def _ipc_get_screenshot(self, *a, **kw):
        return self._ipc_controller._ipc_get_screenshot(*a, **kw)

    def _ipc_set_agg(self, *a, **kw):
        return self._ipc_controller._ipc_set_agg(*a, **kw)

    def _ipc_list_profiles(self, *a, **kw):
        return self._ipc_controller._ipc_list_profiles(*a, **kw)

    def _ipc_create_profile(self, *a, **kw):
        return self._ipc_controller._ipc_create_profile(*a, **kw)

    def _ipc_apply_profile(self, *a, **kw):
        return self._ipc_controller._ipc_apply_profile(*a, **kw)

    def _ipc_delete_profile(self, *a, **kw):
        return self._ipc_controller._ipc_delete_profile(*a, **kw)

    def _ipc_duplicate_profile(self, *a, **kw):
        return self._ipc_controller._ipc_duplicate_profile(*a, **kw)

    def _ipc_start_profile_comparison(self, *a, **kw):
        return self._ipc_controller._ipc_start_profile_comparison(*a, **kw)

    def _ipc_stop_profile_comparison(self, *a, **kw):
        return self._ipc_controller._ipc_stop_profile_comparison(*a, **kw)

    def _ipc_get_profile_comparison_state(self, *a, **kw):
        return self._ipc_controller._ipc_get_profile_comparison_state(*a, **kw)

    def _ipc_set_comparison_sync(self, *a, **kw):
        return self._ipc_controller._ipc_set_comparison_sync(*a, **kw)
