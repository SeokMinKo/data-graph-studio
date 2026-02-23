"""IPC Controller - extracted from MainWindow.

Manages the IPC server and all _ipc_* handler methods.
"""

from __future__ import annotations

import concurrent.futures
import os
import logging
import queue
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, TypeVar

from ...core.state import ChartType, AggregationType, ComparisonMode

if TYPE_CHECKING:
    from ..main_window import MainWindow

logger = logging.getLogger(__name__)

_T = TypeVar("_T")


class IPCController:
    """IPC 서버 관리 컨트롤러"""

    def __init__(self, window: 'MainWindow'):
        self._w = window
        self._work_queue: queue.SimpleQueue = queue.SimpleQueue()

    def setup(self):
        """IPC 서버 설정 - 외부 프로세스에서 앱 제어 가능"""
        from ...core.ipc_server import IPCServer

        self._w._ipc_server = IPCServer(self._w)

        server = self._w._ipc_server

        # 핸들러 등록 — all Qt-touching handlers wrapped with _ui()
        # to ensure they execute on the main thread (IPC runs in background thread)
        ui = self._ui
        server.register_handler('ping', lambda: 'pong')  # pure data, no Qt
        server.register_handler('get_state', ui(self._ipc_get_state))
        server.register_handler('get_data_info', ui(self._ipc_get_data_info))
        server.register_handler('set_chart_type', ui(self._ipc_set_chart_type))
        server.register_handler('set_columns', ui(self._ipc_set_columns))
        server.register_handler('load_file', ui(self._ipc_load_file))
        server.register_handler('get_panels', ui(self._ipc_get_panels))
        server.register_handler('get_summary', ui(self._ipc_get_summary))
        server.register_handler('execute', ui(self._ipc_execute))

        # Zone control handlers
        server.register_handler('set_x_column', ui(self._ipc_set_x_column))
        server.register_handler('set_value_columns', ui(self._ipc_set_value_columns))
        server.register_handler('set_group_columns', ui(self._ipc_set_group_columns))
        server.register_handler('set_hover_columns', ui(self._ipc_set_hover_columns))
        server.register_handler('clear_all_zones', ui(self._ipc_clear_all_zones))
        server.register_handler('get_zones', ui(self._ipc_get_zones))

        # UI control handlers
        server.register_handler('set_theme', ui(self._ipc_set_theme))
        server.register_handler('refresh', ui(self._ipc_refresh))
        server.register_handler('get_screenshot', ui(self._ipc_get_screenshot))
        server.register_handler('set_agg', ui(self._ipc_set_agg))

        # Profile comparison handlers
        server.register_handler('list_profiles', ui(self._ipc_list_profiles))
        server.register_handler('create_profile', ui(self._ipc_create_profile))
        server.register_handler('apply_profile', ui(self._ipc_apply_profile))
        server.register_handler('delete_profile', ui(self._ipc_delete_profile))
        server.register_handler('duplicate_profile', ui(self._ipc_duplicate_profile))
        server.register_handler('start_profile_comparison', ui(self._ipc_start_profile_comparison))
        server.register_handler('stop_profile_comparison', ui(self._ipc_stop_profile_comparison))
        server.register_handler('get_profile_comparison_state', ui(self._ipc_get_profile_comparison_state))
        server.register_handler('set_comparison_sync', ui(self._ipc_set_comparison_sync))

        # Panel capture handler
        self._setup_capture_service()
        server.register_handler('capture', ui(self._ipc_capture))

        # Filter handlers
        server.register_handler('apply_filter', ui(self._ipc_apply_filter))
        server.register_handler('clear_filters', ui(self._ipc_clear_filters))

        # 서버 시작
        server.start()

        # Main-thread pump: drain IPC work items on every Qt event loop tick
        from PySide6.QtCore import QTimer
        self._pump_timer = QTimer(self._w)
        self._pump_timer.timeout.connect(self._pump_work_queue)
        self._pump_timer.start(5)

    # ------------------------------------------------------------------
    # Main-thread dispatcher
    # ------------------------------------------------------------------

    def _main_thread(self, fn: Callable[[], _T], timeout: float = 30.0) -> _T:
        """Execute fn on the Qt main thread and return its result.

        When called from the main thread (e.g., tests), fn runs directly.
        When called from the IPC background thread, the call is queued and
        this method blocks until the main-thread pump drains it.
        """
        if threading.current_thread() is threading.main_thread():
            return fn()
        fut: concurrent.futures.Future = concurrent.futures.Future()
        self._work_queue.put((fn, fut))
        return fut.result(timeout=timeout)

    def _pump_work_queue(self) -> None:
        """Called by QTimer on the main thread — drain pending IPC work."""
        try:
            while True:
                fn, fut = self._work_queue.get_nowait()
                try:
                    fut.set_result(fn())
                except Exception as exc:
                    fut.set_exception(exc)
        except queue.Empty:
            pass

    def _ui(self, fn: Callable) -> Callable:
        """Wrap an IPC handler to execute on the Qt main thread."""
        def wrapper(*args, **kwargs):
            return self._main_thread(lambda: fn(*args, **kwargs))
        return wrapper

    def _setup_capture_service(self) -> None:
        """Initialise CaptureService and register known panel widgets."""
        from ..capture_service import CaptureService

        w = self._w
        self._capture_service = CaptureService()

        for panel_name, attr in [
            ("graph_panel", "graph_panel"),
            ("table_panel", "table_panel"),
            ("summary_panel", "summary_panel"),
        ]:
            widget = getattr(w, attr, None)
            if widget is not None:
                self._capture_service.register_panel(panel_name, widget)

    def _ipc_get_state(self) -> dict:
        """현재 앱 상태 반환"""
        w = self._w
        y_cols = list(w.state._y_columns) if hasattr(w.state, '_y_columns') and w.state._y_columns else []
        return {
            'data_loaded': w.state.is_data_loaded,
            'row_count': w.engine.row_count if w.state.is_data_loaded else 0,
            'columns': w.engine.columns if w.state.is_data_loaded else [],
            'chart_type': w.state._chart_settings.chart_type.name,
            'x_column': w.state.x_column,
            'y_columns': y_cols,
            'window_title': w.windowTitle(),
            'window_size': [w.width(), w.height()],
        }

    def _ipc_get_data_info(self) -> dict:
        """데이터 정보 반환"""
        w = self._w
        if not w.state.is_data_loaded:
            return {'loaded': False}

        return {
            'loaded': True,
            'row_count': w.engine.row_count,
            'columns': w.engine.columns,
            'dtypes': {col: str(dtype) for col, dtype in zip(
                w.engine.columns,
                w.engine.df.dtypes if w.engine.df is not None else []
            )},
        }

    def _ipc_set_chart_type(self, chart_type: str) -> bool:
        """차트 타입 설정"""
        try:
            ct = ChartType[chart_type.upper()]
            self._w.state.set_chart_type(ct)
            return True
        except KeyError:
            raise ValueError(f"Unknown chart type: {chart_type}")

    def _ipc_set_columns(self, x: str = None, y: list = None) -> bool:
        """X/Y 컬럼 설정"""
        w = self._w
        if x:
            w.state.set_x_column(x)
        if y:
            w.state._y_columns = set(y)
            if hasattr(w.state, 'y_columns_changed'):
                w.state.y_columns_changed.emit(y)
        return True

    def _ipc_load_file(self, path: str) -> dict:
        """파일 로드"""
        w = self._w
        if not os.path.exists(path):
            raise FileNotFoundError(f"File not found: {path}")

        dataset_id = w.engine.load_dataset(path)
        if dataset_id:
            dataset = w.engine.get_dataset(dataset_id)
            if dataset:
                w.state.add_dataset(
                    dataset_id=dataset_id,
                    name=dataset.name if dataset.name else Path(path).stem,
                    file_path=path,
                    row_count=dataset.row_count if hasattr(dataset, 'row_count') else w.engine.row_count,
                    column_count=dataset.column_count if hasattr(dataset, 'column_count') else w.engine.column_count,
                    memory_bytes=dataset.memory_bytes if hasattr(dataset, 'memory_bytes') else 0,
                )
            w.state.set_data_loaded(True, w.engine.row_count)
            w.table_panel.set_data(w.engine.df)
            w._on_dataset_activated(dataset_id)
            w._update_summary_from_profile()
            return {'success': True, 'dataset_id': dataset_id}
        return {'success': False}

    def _ipc_get_panels(self) -> dict:
        """패널 정보 반환"""
        w = self._w
        panels = {}
        for name in ['table_panel', 'graph_panel', 'filter_panel', 'property_panel', 'summary_panel']:
            if hasattr(w, name):
                panel = getattr(w, name)
                panels[name] = {
                    'exists': panel is not None,
                    'visible': panel.isVisible() if panel else False,
                }
        return panels

    def _ipc_get_summary(self) -> dict:
        """Summary 통계 반환"""
        w = self._w
        summary = w.engine.get_full_profile_summary()
        profile = w.engine.profile

        if summary is None and profile is None:
            return {}

        if summary is None and profile is not None:
            numeric_cols = sum(1 for c in profile.columns if c.is_numeric)
            text_cols = sum(1 for c in profile.columns if not c.is_numeric and not c.is_temporal)
            temporal_cols = sum(1 for c in profile.columns if c.is_temporal)

            total_cells = profile.total_rows * profile.total_columns
            total_nulls = sum(c.null_count for c in profile.columns)
            missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0

            summary = {
                'total_rows': profile.total_rows,
                'total_columns': profile.total_columns,
                'numeric_columns': numeric_cols,
                'text_columns': text_cols + temporal_cols,
                'missing_percent': missing_percent,
                'memory_bytes': profile.memory_bytes,
                'load_time_seconds': profile.load_time_seconds,
            }

        # file name
        if w.engine._source and w.engine._source.path:
            summary['file_name'] = Path(w.engine._source.path).name

        return summary

    def _ipc_execute(self, code: str) -> Any:
        """Python 코드 실행 (디버깅용)"""
        w = self._w
        local_vars = {
            'window': w,
            'state': w.state,
            'engine': w.engine,
            'table_panel': w.table_panel,
            'graph_panel': w.graph_panel,
            'summary_panel': w.summary_panel,
        }
        import builtins as _builtins
        return eval(code, {'__builtins__': _builtins}, local_vars)

    # ==================== IPC Zone Control Handlers ====================

    def _ipc_set_x_column(self, column: str) -> dict:
        """X 컬럼 설정."""
        w = self._w
        try:
            if column == "(Index)":
                w.state.set_x_column(None)
            else:
                if w.state.is_data_loaded and column not in w.engine.columns:
                    raise ValueError(f"Column not found: {column}")
                w.state.set_x_column(column)
            return {"success": True, "x_column": w.state.x_column}
        except Exception as e:
            raise ValueError(f"Failed to set x column: {e}")

    def _ipc_set_value_columns(self, columns: list) -> dict:
        """Value zone 설정."""
        w = self._w
        try:
            if w.state.is_data_loaded:
                available = set(w.engine.columns)
                invalid = [c for c in columns if c not in available]
                if invalid:
                    raise ValueError(f"Columns not found: {invalid}")

            w.state.clear_value_zone()
            for col in columns:
                w.state.add_value_column(col)

            return {
                "success": True,
                "value_columns": [vc.name for vc in w.state.value_columns],
            }
        except Exception as e:
            raise ValueError(f"Failed to set value columns: {e}")

    def _ipc_set_group_columns(self, columns: list) -> dict:
        """Group zone 설정."""
        w = self._w
        try:
            if w.state.is_data_loaded:
                available = set(w.engine.columns)
                invalid = [c for c in columns if c not in available]
                if invalid:
                    raise ValueError(f"Columns not found: {invalid}")

            w.state.clear_group_zone()
            for col in columns:
                w.state.add_group_column(col)

            return {
                "success": True,
                "group_columns": [gc.name for gc in w.state.group_columns],
            }
        except Exception as e:
            raise ValueError(f"Failed to set group columns: {e}")

    def _ipc_set_hover_columns(self, columns: list) -> dict:
        """Hover zone 설정."""
        w = self._w
        try:
            if w.state.is_data_loaded:
                available = set(w.engine.columns)
                invalid = [c for c in columns if c not in available]
                if invalid:
                    raise ValueError(f"Columns not found: {invalid}")

            w.state.clear_hover_columns()
            for col in columns:
                w.state.add_hover_column(col)

            return {
                "success": True,
                "hover_columns": list(w.state.hover_columns),
            }
        except Exception as e:
            raise ValueError(f"Failed to set hover columns: {e}")

    def _ipc_clear_all_zones(self) -> dict:
        """모든 zone 비우기."""
        w = self._w
        try:
            w.state.set_x_column(None)
            w.state.clear_value_zone()
            w.state.clear_group_zone()
            w.state.clear_hover_columns()
            return {"success": True}
        except Exception as e:
            raise ValueError(f"Failed to clear zones: {e}")

    def _ipc_get_zones(self) -> dict:
        """현재 각 zone의 상태 반환."""
        state = self._w.state
        return {
            "x_column": state.x_column,
            "value_columns": [
                {"name": vc.name, "aggregation": vc.aggregation.value}
                for vc in state.value_columns
            ],
            "group_columns": [
                {"name": gc.name}
                for gc in state.group_columns
            ],
            "hover_columns": list(state.hover_columns),
            "chart_type": state._chart_settings.chart_type.value if hasattr(state, '_chart_settings') else None,
        }

    def _ipc_set_theme(self, theme_id: str) -> dict:
        """테마 변경."""
        valid_themes = ("light", "dark", "midnight")
        if theme_id not in valid_themes:
            raise ValueError(f"Invalid theme_id: {theme_id}. Must be one of {valid_themes}")
        self._w._on_theme_changed(theme_id)
        return {"success": True, "theme": theme_id}

    def _ipc_refresh(self) -> dict:
        """GraphPanel 강제 리프레시."""
        try:
            self._w.graph_panel.refresh()
            return {"success": True}
        except Exception as e:
            raise ValueError(f"Failed to refresh: {e}")

    def _ipc_get_screenshot(self, path: str = "/tmp/dgs_screenshot.png") -> dict:
        """앱 윈도우를 캡처해서 지정된 경로에 저장."""
        try:
            pixmap = self._w.grab()
            pixmap.save(path)
            return {
                "success": True,
                "path": path,
                "width": pixmap.width(),
                "height": pixmap.height(),
            }
        except Exception as e:
            raise ValueError(f"Failed to take screenshot: {e}")

    def _ipc_set_agg(self, agg1: str, agg2: str = None) -> dict:
        """Value column의 aggregation 타입 변경."""
        w = self._w
        try:
            vcs = w.state.value_columns
            if not vcs:
                raise ValueError("No value columns configured")

            agg1_type = AggregationType(agg1.lower())
            w.state.update_value_column(0, aggregation=agg1_type)

            if agg2 is not None and len(vcs) >= 2:
                agg2_type = AggregationType(agg2.lower())
                w.state.update_value_column(1, aggregation=agg2_type)

            return {
                "success": True,
                "value_columns": [
                    {"name": vc.name, "aggregation": vc.aggregation.value}
                    for vc in w.state.value_columns
                ],
            }
        except Exception as e:
            raise ValueError(f"Failed to set aggregation: {e}")

    # ==================== IPC Profile Comparison Handlers ====================

    def _ipc_list_profiles(self, dataset_id: str = None) -> list:
        """List all profiles (GraphSettings) for a dataset."""
        w = self._w
        did = dataset_id or w.state.active_dataset_id
        if not did:
            raise ValueError("No active dataset")
        settings = w.profile_store.get_by_dataset(did)
        return [
            {
                "id": s.id,
                "name": s.name,
                "dataset_id": s.dataset_id,
                "chart_type": s.chart_type,
                "x_column": s.x_column,
                "value_columns": list(s.value_columns),
            }
            for s in settings
        ]

    def _ipc_create_profile(self, name: str, dataset_id: str = None) -> dict:
        """Create a new profile from current state."""
        w = self._w
        did = dataset_id or w.state.active_dataset_id
        if not did:
            raise ValueError("No active dataset")
        profile_id = w.profile_controller.create_profile(did, name)
        if profile_id is None:
            raise RuntimeError("Failed to create profile")
        setting = w.profile_store.get(profile_id)
        return {"id": setting.id, "name": setting.name}

    def _ipc_apply_profile(self, profile_id: str) -> dict:
        """Apply a profile to the current view."""
        w = self._w
        ok = w.profile_controller.apply_profile(profile_id)
        if not ok:
            raise ValueError(f"Failed to apply profile: {profile_id}")
        w._schedule_autofit()
        return {"ok": True}

    def _ipc_delete_profile(self, profile_id: str) -> dict:
        """Delete a profile."""
        ok = self._w.profile_controller.delete_profile(profile_id)
        if not ok:
            raise ValueError(f"Failed to delete profile: {profile_id}")
        return {"ok": True}

    def _ipc_duplicate_profile(self, profile_id: str) -> dict:
        """Duplicate a profile."""
        w = self._w
        new_id = w.profile_controller.duplicate_profile(profile_id)
        if new_id is None:
            raise ValueError(f"Failed to duplicate profile: {profile_id}")
        setting = w.profile_store.get(new_id)
        return {"id": setting.id, "name": setting.name}

    def _ipc_start_profile_comparison(self, profile_ids: list, mode: str = "side_by_side") -> dict:
        """Start comparing profiles via ProfileComparisonController."""
        w = self._w
        comp_mode = {
            "side_by_side": ComparisonMode.SIDE_BY_SIDE,
            "overlay": ComparisonMode.OVERLAY,
            "difference": ComparisonMode.DIFFERENCE,
        }.get(mode)
        if comp_mode is None:
            raise ValueError(f"Invalid comparison mode: {mode}")

        if not profile_ids:
            raise ValueError("At least 2 profiles required for comparison")
        first = w.profile_store.get(profile_ids[0])
        if first is None:
            raise ValueError(f"Profile not found: {profile_ids[0]}")
        dataset_id = first.dataset_id

        ok = w.profile_comparison_controller.start_comparison(
            dataset_id, profile_ids, comp_mode,
        )
        if not ok:
            raise ValueError("Profile comparison validation failed")

        return {"ok": True, "mode": mode}

    def _ipc_stop_profile_comparison(self) -> dict:
        """Stop comparison, return to single view."""
        self._w.profile_comparison_controller.stop_comparison()
        return {"ok": True}

    def _ipc_get_profile_comparison_state(self) -> dict:
        """Get current comparison status."""
        w = self._w
        pcc = w.profile_comparison_controller
        cs = w.state.comparison_settings
        return {
            "active": pcc.is_active,
            "mode": pcc.current_mode.value,
            "target": cs.comparison_target,
            "profile_ids": list(pcc.current_profiles),
            "dataset_id": pcc.dataset_id,
            "sync_x": cs.sync_pan_x,
            "sync_y": cs.sync_pan_y,
            "sync_selection": cs.sync_selection,
        }

    def _ipc_set_comparison_sync(
        self,
        sync_x: bool = None,
        sync_y: bool = None,
        sync_selection: bool = None,
    ) -> dict:
        """Toggle sync options."""
        w = self._w
        if sync_x is not None:
            w.state._comparison_settings.sync_pan_x = sync_x
        if sync_y is not None:
            w.state._comparison_settings.sync_pan_y = sync_y
        if sync_selection is not None:
            w.state._comparison_settings.sync_selection = sync_selection
        w.state.comparison_settings_changed.emit()
        return {"ok": True}

    # ==================== IPC Filter Handlers ====================

    def _ipc_apply_filter(self, column: str, op: str, value: Any) -> dict:
        """
        Add a filter condition to the active dataset.

        Inputs: column (str), op ("eq","gt","lt","contains","neq"), value (Any)
        Outputs: {"status": "ok", ...} or {"status": "error", "message": ...}
        """
        try:
            self._w.state.add_filter(column, op, value)
            return {"status": "ok", "column": column, "op": op, "value": value}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    def _ipc_clear_filters(self) -> dict:
        """
        Remove all active filters.

        Outputs: {"status": "ok"} or {"status": "error", "message": ...}
        """
        try:
            self._w.state.clear_filters()
            return {"status": "ok"}
        except Exception as exc:
            return {"status": "error", "message": str(exc)}

    # ==================== IPC Capture Handler ====================

    def _ipc_capture(
        self,
        target: str = "all",
        output_dir: str = "/tmp/dgs_captures",
        format: str = "png",
    ) -> dict:
        """Capture one or more panels and return serialisable results."""
        import dataclasses
        from ...core.capture_protocol import CaptureRequest

        req = CaptureRequest(target=target, output_dir=Path(output_dir), format=format)
        results = self._capture_service.capture(req)
        serialised = []
        for r in results:
            d = dataclasses.asdict(r)
            d["file"] = str(d["file"])
            serialised.append(d)
        return {"status": "ok", "captures": serialised}
