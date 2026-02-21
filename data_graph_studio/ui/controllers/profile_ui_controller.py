"""Profile UI Controller - extracted from MainWindow.

Handles profile menu actions, profile CRUD via ProjectTreeView,
profile comparison requests, profile autosave, and profile file I/O.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtWidgets import (
    QFileDialog, QMessageBox, QInputDialog, QDialog,
)

from ...core.profile import Profile, GraphSetting
from ...core.state import ComparisonMode

if TYPE_CHECKING:
    from ..main_window import MainWindow

logger = logging.getLogger(__name__)


class ProfileUIController:
    """프로필 UI 관리 컨트롤러"""

    def __init__(self, window: 'MainWindow'):
        self._w = window

    # ==================== Profile Menu Actions ====================

    def _on_new_profile_menu(self):
        """메뉴에서 새 프로파일"""
        w = self._w
        name, ok = QInputDialog.getText(
            w, "New Profile", "Enter profile name:", text="New Profile"
        )
        if ok and name.strip():
            profile = Profile.create_new(name.strip())
            w.state.set_profile(profile)
            w.statusbar.showMessage(f"Created new profile: {name.strip()}", 3000)

    def _on_load_profile_menu(self):
        """메뉴에서 프로파일 로드"""
        w = self._w
        path, _ = QFileDialog.getOpenFileName(
            w, "Load Profile",
            str(w.profile_bar.profile_manager.profiles_dir),
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile = w.profile_bar.profile_manager.load(path)
                w.state.set_profile(profile)
                w.statusbar.showMessage(f"Loaded profile: {profile.name}", 3000)
            except Exception as e:
                QMessageBox.critical(w, "Load Profile Error", f"Failed to load profile: {e}")

    def _on_save_profile_menu(self):
        """메뉴에서 프로파일 저장"""
        w = self._w
        profile = w.state.current_profile
        if not profile:
            QMessageBox.information(w, "Save Profile", "No profile to save. Create a new profile first.")
            return

        path, _ = QFileDialog.getSaveFileName(
            w, "Save Profile",
            str(w.profile_bar.profile_manager.profiles_dir / f"{profile.name}.dgp"),
            "Data Graph Profile (*.dgp)"
        )
        if path:
            try:
                profile.save(path)
                w.profile_bar.profile_manager._add_recent_profile(path)
                w.state.profile_saved.emit()
                w.statusbar.showMessage(f"Profile saved: {profile.name}", 3000)
            except Exception as e:
                QMessageBox.critical(w, "Save Profile Error", f"Failed to save profile: {e}")

    # ==================== Profile Actions (ProfileBar) ====================

    def _on_profile_setting_clicked(self, setting_id: str):
        """프로파일 설정 클릭"""
        w = self._w
        profile = w.state.current_profile
        if profile:
            setting = profile.get_setting(setting_id)
            if setting:
                w.state.apply_graph_setting(setting)
                w.state.activate_setting(setting_id)
                w.graph_panel.refresh()

    def _on_profile_setting_double_clicked(self, setting_id: str):
        """프로파일 설정 더블클릭 (Floating 창 열기)"""
        w = self._w
        profile = w.state.current_profile
        if profile and w._floating_graph_manager:
            setting = profile.get_setting(setting_id)
            if setting:
                w._floating_graph_manager.open_floating_graph(setting, w)

    def _on_add_setting_requested(self):
        """새 설정 추가 요청"""
        w = self._w
        if not w.state.current_profile:
            name, ok = QInputDialog.getText(
                w, "New Profile",
                "No profile loaded. Create a new profile first.\n\nEnter profile name:",
                text="New Profile"
            )
            if not ok or not name.strip():
                return
            profile = Profile.create_new(name.strip())
            w.state.set_profile(profile)

        from ..dialogs.save_setting_dialog import SaveSettingDialog
        dialog = SaveSettingDialog(w)
        if dialog.exec() == QDialog.Accepted:
            setting = dialog.get_setting()
            if setting:
                from dataclasses import replace
                graph_state = w.state.get_current_graph_state()

                include_filters = dialog.get_include_filters()
                include_sorts = dialog.get_include_sorts()

                setting = replace(
                    setting,
                    chart_type=graph_state['chart_type'],
                    x_column=graph_state['x_column'],
                    group_columns=tuple(graph_state['group_columns']),
                    value_columns=tuple(graph_state['value_columns']),
                    hover_columns=tuple(graph_state['hover_columns']),
                    chart_settings=graph_state['chart_settings'],
                    filters=tuple(graph_state['filters']) if include_filters else setting.filters,
                    sorts=tuple(graph_state['sorts']) if include_sorts else setting.sorts,
                    include_filters=include_filters,
                    include_sorts=include_sorts,
                )

                w.state.add_setting(setting)
                w.statusbar.showMessage(f"Setting '{setting.name}' saved", 3000)

    def _on_compare_profiles_requested(self):
        """Compare Profiles 버튼 클릭"""
        w = self._w
        from ..dialogs.profile_comparison_dialog import ProfileComparisonDialog

        dataset_id = w.state.active_dataset_id or ""
        profiles = w.profile_store.get_by_dataset(dataset_id) if dataset_id else []

        if len(profiles) < 2:
            QMessageBox.information(
                w, "Compare Profiles",
                "Create at least 2 profiles for the current dataset to compare.",
            )
            return

        dialog = ProfileComparisonDialog(profiles, w)
        if dialog.exec() == QDialog.Accepted:
            ids = dialog.selected_profile_ids
            mode = dialog.selected_mode
            if len(ids) >= 2:
                w.profile_comparison_controller.start_comparison(dataset_id, ids, mode)

    def _show_profile_manager(self):
        """프로파일 관리자 다이얼로그 표시"""
        from ..dialogs.profile_manager_dialog import ProfileManagerDialog
        w = self._w
        dialog = ProfileManagerDialog(w.profile_bar.profile_manager, w)
        dialog.exec()

    # ==================== Project Explorer Actions ====================

    def _on_profile_apply_requested(self, profile_id: str):
        """프로파일 적용 요청 (ProjectTreeView에서)"""
        w = self._w
        if w.profile_controller.apply_profile(profile_id):
            w.graph_panel.refresh()
            w._schedule_autofit()
            w.statusbar.showMessage("Profile applied", 2000)

    def _on_new_profile_requested(self, dataset_id: str):
        """새 프로파일 생성 요청"""
        w = self._w
        name, ok = QInputDialog.getText(
            w, "New Profile", "Enter profile name:", text="New Profile"
        )
        if ok and name.strip():
            profile_id = w.profile_controller.create_profile(dataset_id, name.strip())
            if profile_id:
                setting = w.profile_store.get(profile_id)
                if setting:
                    w.profile_model.add_profile_incremental(dataset_id, setting)
                else:
                    w.profile_model.refresh()
                w.graph_panel.refresh()
                w._schedule_autofit()
                w.statusbar.showMessage(f"Profile '{name}' created", 2000)

    def _on_profile_rename_requested(self, profile_id: str):
        """프로파일 이름 변경 요청"""
        w = self._w
        setting = w.profile_store.get(profile_id)
        if not setting:
            return
        name, ok = QInputDialog.getText(
            w, "Rename Profile", "Enter new name:", text=setting.name
        )
        if ok and name.strip():
            w.state.blockSignals(True)
            try:
                if w.profile_controller.rename_profile(profile_id, name.strip()):
                    updated = w.profile_store.get(profile_id)
                    if updated:
                        w.profile_model.update_profile_data(updated.dataset_id, updated)
                    else:
                        w.profile_model.refresh()
                    w.statusbar.showMessage("Profile renamed", 2000)
            finally:
                w.state.blockSignals(False)

    def _on_profile_delete_requested(self, profile_id: str):
        """프로파일 삭제 요청"""
        w = self._w
        setting = w.profile_store.get(profile_id)
        if not setting:
            return
        dataset_id = setting.dataset_id
        reply = QMessageBox.question(
            w, "Delete Profile",
            f"Delete profile '{setting.name}'?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if w.profile_controller.delete_profile(profile_id):
                w.profile_model.remove_profile_incremental(dataset_id, profile_id)
                w.statusbar.showMessage("Profile deleted (Ctrl+Z to undo)", 3000)

    def _on_profile_duplicate_requested(self, profile_id: str):
        """프로파일 복제 요청"""
        w = self._w
        new_id = w.profile_controller.duplicate_profile(profile_id)
        if new_id:
            new_setting = w.profile_store.get(new_id)
            if new_setting:
                w.profile_model.add_profile_incremental(new_setting.dataset_id, new_setting)
            else:
                w.profile_model.refresh()
            w.statusbar.showMessage("Profile duplicated", 2000)

    def _on_profile_export_requested(self, profile_id: str):
        """프로파일 내보내기 요청"""
        w = self._w
        setting = w.profile_store.get(profile_id)
        if not setting:
            return
        path, _ = QFileDialog.getSaveFileName(
            w, "Export Profile", f"{setting.name}.dgp", "Data Graph Profile (*.dgp)"
        )
        if path:
            if w.profile_controller.export_profile(profile_id, path):
                w.statusbar.showMessage(f"Profile exported to {path}", 3000)

    def _on_profile_import_requested(self, dataset_id: str):
        """프로파일 가져오기 요청"""
        w = self._w
        path, _ = QFileDialog.getOpenFileName(
            w, "Import Profile", "", "Data Graph Profile (*.dgp)"
        )
        if path:
            profile_id = w.profile_controller.import_profile(dataset_id, path)
            if profile_id:
                imported_setting = w.profile_store.get(profile_id)
                if imported_setting:
                    w.profile_model.add_profile_incremental(dataset_id, imported_setting)
                else:
                    w.profile_model.refresh()
                w.statusbar.showMessage("Profile imported", 2000)

    def _on_profile_compare_requested(self, profile_ids: list, options: dict):
        """프로젝트 탐색창에서 멀티 선택 → Compare 요청"""
        w = self._w
        if len(profile_ids) < 2:
            return

        first = w.profile_store.get(profile_ids[0])
        if not first:
            return
        dataset_id = first.dataset_id

        cs = w.state._comparison_settings
        cs.sync_pan_x = options.get("x_sync", True)
        cs.sync_pan_y = options.get("y_sync", True)
        cs.sync_zoom = options.get("zoom_sync", True)
        cs.sync_selection = options.get("selection_sync", True)

        mode_map = {
            "side_by_side": ComparisonMode.SIDE_BY_SIDE,
            "overlay": ComparisonMode.OVERLAY,
            "difference": ComparisonMode.DIFFERENCE,
        }
        mode = mode_map.get(options.get("mode", "side_by_side"), ComparisonMode.SIDE_BY_SIDE)

        w.profile_comparison_controller.start_comparison(dataset_id, profile_ids, mode)

    # ==================== Cross-dataset Copy & Favorite ====================

    def _on_copy_to_dataset_requested(self, profile_id: str):
        """프로파일을 다른 데이터셋으로 복사"""
        w = self._w
        setting = w.profile_store.get(profile_id)
        if not setting:
            return

        all_datasets = list(w.state.dataset_metadata.keys())
        current_ds = setting.dataset_id
        other_datasets = [ds for ds in all_datasets if ds != current_ds]

        if not other_datasets:
            QMessageBox.information(w, "Copy Profile", "No other datasets available.")
            return

        names = []
        for ds_id in other_datasets:
            meta = w.state.dataset_metadata.get(ds_id)
            names.append(meta.name if meta else ds_id)

        name, ok = QInputDialog.getItem(
            w, "Copy Profile",
            f"Copy '{setting.name}' to which dataset?",
            names, 0, False,
        )
        if ok and name:
            import uuid
            import dataclasses

            target_idx = names.index(name)
            target_ds = other_datasets[target_idx]

            new_setting = dataclasses.replace(
                setting,
                id=str(uuid.uuid4()),
                dataset_id=target_ds,
                name=f"{setting.name} (copy)",
            )
            w.profile_store.add(new_setting)
            w.profile_model.add_profile_incremental(target_ds, new_setting)
            w.statusbar.showMessage(f"Profile copied to {name}", 3000)

    def _on_favorite_toggled(self, profile_id: str):
        """프로파일 즐겨찾기 토글"""
        w = self._w
        setting = w.profile_store.get(profile_id)
        if not setting:
            return
        import dataclasses

        updated = dataclasses.replace(setting, is_favorite=not setting.is_favorite)
        w.profile_store.update(updated)
        w.profile_model.update_profile_data(updated.dataset_id, updated)

    # ==================== Profile Comparison ====================

    def _on_profile_comparison_started(self, mode_value: str, profile_ids: list):
        """Handle profile comparison started — delegate to dataset controller."""
        self._w._dataset_controller._on_profile_comparison_started(mode_value, profile_ids)

    def _on_profile_comparison_ended(self):
        """Handle profile comparison ended — delegate to dataset controller."""
        self._w._dataset_controller._on_profile_comparison_ended()

    # ==================== Profile Autosave ====================

    def _schedule_profile_autosave(self):
        """Schedule debounced auto-save of active profile"""
        self._w._profile_autosave_timer.start()

    def _autosave_active_profile(self):
        """Auto-save current AppState to active profile"""
        w = self._w
        if hasattr(w, 'profile_controller'):
            w.profile_controller.save_active_profile()
            # Show auto-saved feedback
            active_id = getattr(w.state, 'active_setting_id', None)
            if active_id and hasattr(w, 'profile_store'):
                setting = w.profile_store.get(active_id)
                if setting:
                    w.statusbar.showMessage(f"Auto-saved to '{setting.name}'", 2000)

    # ==================== Profile File I/O ====================

    def _on_open_profile(self):
        """Open Profile – 단일 프로파일 JSON 파일 로드"""
        w = self._w
        file_path, _ = QFileDialog.getOpenFileName(
            w, "Open Profile",
            str(Path.home()),
            "DGS Profile (*.dgs-profile);;JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            gs = GraphSetting.from_dict(data)
            dataset_id = w.state.active_dataset_id or ""
            if gs.dataset_id != dataset_id:
                from dataclasses import replace as _replace
                gs = _replace(gs, dataset_id=dataset_id)
            w.profile_store.add(gs)
            w._last_profile_path = file_path
            if hasattr(w, 'profile_model'):
                w.profile_model.refresh()
            w.statusbar.showMessage(f"Profile loaded: {gs.name}", 3000)
        except Exception as e:
            QMessageBox.warning(w, "Open Profile", f"Failed to load profile:\n{e}")

    def _on_save_profile_file(self):
        """Save Profile – 활성 프로파일을 마지막 경로로 저장"""
        w = self._w
        dataset_id = w.state.active_dataset_id or ""
        settings = w.profile_store.get_by_dataset(dataset_id)
        if not settings:
            QMessageBox.information(w, "Save Profile", "No active profile to save.")
            return

        gs = settings[0]
        path = getattr(w, '_last_profile_path', None)
        if not path:
            return self._on_save_profile_file_as()
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(gs.to_dict(), f, indent=2, ensure_ascii=False)
            w.statusbar.showMessage(f"Profile saved: {path}", 3000)
        except Exception as e:
            QMessageBox.warning(w, "Save Profile", f"Failed to save profile:\n{e}")

    def _on_save_profile_file_as(self):
        """Save Profile As – 프로파일을 새 경로에 JSON으로 저장"""
        w = self._w
        dataset_id = w.state.active_dataset_id or ""
        settings = w.profile_store.get_by_dataset(dataset_id)
        if not settings:
            QMessageBox.information(w, "Save Profile As", "No active profile to save.")
            return

        gs = settings[0]
        default_name = gs.name.replace(' ', '_') if gs.name else "profile"
        file_path, _ = QFileDialog.getSaveFileName(
            w, "Save Profile As",
            str(Path.home() / f"{default_name}.dgs-profile"),
            "DGS Profile (*.dgs-profile);;JSON Files (*.json);;All Files (*.*)"
        )
        if not file_path:
            return
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(gs.to_dict(), f, indent=2, ensure_ascii=False)
            w._last_profile_path = file_path
            w.statusbar.showMessage(f"Profile saved: {file_path}", 3000)
        except Exception as e:
            QMessageBox.warning(w, "Save Profile As", f"Failed to save profile:\n{e}")

    def _on_save_profile_bundle_as(self):
        """Save Profile Bundle As – 모든 프로파일을 .dgs-bundle JSON으로 저장"""
        w = self._w
        file_path, _ = QFileDialog.getSaveFileName(
            w, "Save Profile Bundle As",
            str(Path.home() / "profiles.dgs-bundle"),
            "DGS Profile Bundle (*.dgs-bundle);;All Files (*.*)"
        )
        if not file_path:
            return
        try:
            all_profiles = []
            for did in w.engine.get_dataset_ids() if hasattr(w.engine, 'get_dataset_ids') else [""]:
                for gs in w.profile_store.get_by_dataset(did):
                    all_profiles.append(gs.to_dict())
            for gs in w.profile_store.get_by_dataset(""):
                all_profiles.append(gs.to_dict())
            seen_ids = set()
            unique = []
            for p in all_profiles:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    unique.append(p)

            bundle = {
                "format": "dgs-profile-bundle",
                "version": "1.0",
                "profiles": unique,
            }
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(bundle, f, indent=2, ensure_ascii=False)
            w.statusbar.showMessage(f"Profile bundle saved: {file_path} ({len(unique)} profiles)", 3000)
        except Exception as e:
            QMessageBox.warning(w, "Save Profile Bundle", f"Failed to save bundle:\n{e}")

    # ==================== Project I/O ====================

    def _on_open_project(self):
        """Open Project – .dgs 프로젝트 파일 로드 (데이터소스 + 프로파일)"""
        w = self._w
        file_path, _ = QFileDialog.getOpenFileName(
            w, "Open Project",
            str(Path.home()),
            "DGS Project (*.dgs);;All Files (*.*)"
        )
        if not file_path:
            return
        # file_loading_controller의 전체 프로젝트 로드 사용
        w._file_controller._load_project_file(file_path)

    def _on_save_project_file(self):
        """Save Project – 프로젝트+프로파일 저장 (마지막 경로)"""
        w = self._w
        path = getattr(w, '_last_project_path', None)
        if not path:
            return self._on_save_project_file_as()
        self._save_project_to(path)

    def _on_save_project_file_as(self):
        """Save Project As – 프로젝트+프로파일을 새 경로에 .dgs로 저장"""
        w = self._w
        file_path, _ = QFileDialog.getSaveFileName(
            w, "Save Project As",
            str(Path.home() / "project.dgs"),
            "DGS Project (*.dgs);;All Files (*.*)"
        )
        if not file_path:
            return
        self._save_project_to(file_path)

    def _save_project_to(self, path: str):
        """프로젝트를 지정 경로에 저장"""
        from ...core.project import Project, DataSourceRef
        w = self._w
        try:
            project = Project(name=Path(path).stem)
            project_dir = Path(path).parent

            for dataset_id in w.engine.get_dataset_ids() if hasattr(w.engine, 'get_dataset_ids') else []:
                dataset = w.engine.get_dataset(dataset_id)
                if dataset:
                    source_path = getattr(dataset, 'source_path', None) or getattr(dataset, 'file_path', None)
                    if source_path and os.path.exists(source_path):
                        try:
                            rel_path = os.path.relpath(source_path, project_dir)
                        except ValueError:
                            rel_path = source_path
                        ds_ref = DataSourceRef(
                            path=rel_path,
                            file_type=Path(source_path).suffix.lstrip('.'),
                            dataset_id=dataset_id,
                            name=getattr(dataset, 'name', None),
                            is_active=(dataset_id == w.state.active_dataset_id),
                        )
                        project.add_data_source(ds_ref)

            all_profiles = []
            for did in w.engine.get_dataset_ids() if hasattr(w.engine, 'get_dataset_ids') else [""]:
                for gs in w.profile_store.get_by_dataset(did):
                    all_profiles.append(gs.to_dict())
            for gs in w.profile_store.get_by_dataset(""):
                all_profiles.append(gs.to_dict())
            seen_ids = set()
            unique = []
            for p in all_profiles:
                if p["id"] not in seen_ids:
                    seen_ids.add(p["id"])
                    unique.append(p)
            project.profiles = unique

            project.save(path)
            w._last_project_path = path
            ds_count = len(project.data_sources)
            w.statusbar.showMessage(f"Project saved: {path} ({ds_count} datasets, {len(unique)} profiles)", 3000)
        except Exception as e:
            QMessageBox.warning(w, "Save Project", f"Failed to save project:\n{e}")

    # ==================== Summary ====================

    def _update_summary_from_profile(self):
        """프로파일에서 Summary 업데이트"""
        w = self._w
        if not w.engine.profile:
            return

        profile = w.engine.profile
        summary = w.engine.get_full_profile_summary()
        if summary is None and profile is None:
            return

        file_name = ""
        if w.engine._source and w.engine._source.path:
            file_name = Path(w.engine._source.path).name

        if summary is None and profile is not None:
            numeric_cols = sum(1 for c in profile.columns if c.is_numeric)
            text_cols = sum(1 for c in profile.columns if not c.is_numeric and not c.is_temporal)
            temporal_cols = sum(1 for c in profile.columns if c.is_temporal)

            total_cells = profile.total_rows * profile.total_columns
            total_nulls = sum(c.null_count for c in profile.columns)
            missing_percent = (total_nulls / total_cells * 100) if total_cells > 0 else 0

            total_rows = profile.total_rows
            total_columns = profile.total_columns
            numeric_columns = numeric_cols
            text_columns = text_cols + temporal_cols
            memory_mb = profile.memory_bytes / (1024 * 1024)
            load_time = profile.load_time_seconds
        else:
            total_rows = summary.get('total_rows', 0)
            total_columns = summary.get('total_columns', 0)
            numeric_columns = summary.get('numeric_columns', 0)
            text_columns = summary.get('text_columns', 0)
            missing_percent = summary.get('missing_percent', 0)
            memory_mb = summary.get('memory_bytes', 0) / (1024 * 1024) if summary else 0
            load_time = summary.get('load_time_seconds', 0) if summary else 0

        MAX_GRAPH_POINTS = 10000
        sampled_rows = min(total_rows, MAX_GRAPH_POINTS)

        stats = {
            'file_name': file_name,
            'total_rows': total_rows,
            'sampled_rows': sampled_rows,
            'total_columns': total_columns,
            'numeric_columns': numeric_columns,
            'text_columns': text_columns,
            'missing_percent': missing_percent,
            'memory_mb': memory_mb,
            'load_time': load_time,
        }

        if profile is not None:
            for col_info in profile.columns:
                if col_info.is_numeric:
                    stats[col_info.name] = {
                        'min': col_info.min_value,
                        'max': col_info.max_value,
                        'null_count': col_info.null_count,
                    }

        try:
            x_col = w.state.x_column
            if x_col and w.engine.df is not None and x_col in w.engine.df.columns:
                x_series = w.engine.df[x_col]
                try:
                    x_min = float(x_series.min())
                    x_max = float(x_series.max())
                    stats['x_range'] = {'min': x_min, 'max': x_max, 'range': x_max - x_min, 'column': x_col}
                except (TypeError, ValueError):
                    pass

            if w.state.value_columns and w.engine.df is not None:
                y_min_all, y_max_all = float('inf'), float('-inf')
                y_col_names = []
                for vc in w.state.value_columns:
                    name = vc.name if hasattr(vc, 'name') else str(vc)
                    if name in w.engine.df.columns:
                        y_col_names.append(name)
                        try:
                            col_min = float(w.engine.df[name].min())
                            col_max = float(w.engine.df[name].max())
                            y_min_all = min(y_min_all, col_min)
                            y_max_all = max(y_max_all, col_max)
                        except (TypeError, ValueError):
                            pass
                if y_min_all < float('inf') and y_max_all > float('-inf'):
                    stats['y_range'] = {
                        'min': y_min_all, 'max': y_max_all,
                        'range': y_max_all - y_min_all,
                        'columns': y_col_names,
                    }
        except Exception:
            pass

        w.state.update_summary(stats)
