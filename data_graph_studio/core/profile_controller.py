"""ProfileController - orchestrates GraphSetting operations."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Optional, List, Dict, Any

from PySide6.QtCore import QObject, Signal

from .graph_setting_mapper import GraphSettingMapper
from .profile import GraphSetting
from .profile_store import ProfileStore
from .state import AppState
from .undo_manager import UndoStack, UndoCommand, UndoActionType


class ProfileController(QObject):
    profile_applied = Signal(str)
    profile_created = Signal(str)
    profile_deleted = Signal(str)
    profile_renamed = Signal(str, str)
    error_occurred = Signal(str)

    def __init__(self, store: ProfileStore, state: AppState, undo_stack: Optional[UndoStack] = None):
        super().__init__()
        self._store = store
        self._state = state
        self._active_profile_id: Optional[str] = None
        self._main_undo_stack: Optional[UndoStack] = undo_stack

    def create_profile(self, dataset_id: str, name: str) -> Optional[str]:
        try:
            # 새 프로파일 생성 전에 현재 활성 프로파일의 변경사항 자동 저장
            if self._active_profile_id:
                self.save_active_profile()

            import uuid
            setting = GraphSetting(
                id=str(uuid.uuid4()),
                name=name,
                dataset_id=dataset_id,
            )
            self._store.add(setting)
            # 새 프로파일을 활성화하고 빈 상태를 AppState에 적용
            self._active_profile_id = setting.id
            GraphSettingMapper.to_app_state(setting, self._state)
            self.profile_created.emit(setting.id)
            return setting.id
        except Exception as exc:  # pragma: no cover - defensive
            self.error_occurred.emit(str(exc))
            return None

    def save_active_profile(self) -> bool:
        """현재 AppState를 활성 프로파일에 저장 (auto-save)."""
        if not self._active_profile_id:
            return False
        setting = self._store.get(self._active_profile_id)
        if setting is None:
            return False
        updated = GraphSettingMapper.from_app_state(
            self._state, name=setting.name, dataset_id=setting.dataset_id,
        )
        # 기존 id, created_at 유지, modified_at 갱신
        import time as _time
        updated = replace(
            updated,
            id=setting.id,
            created_at=setting.created_at,
            modified_at=_time.time(),
        )
        self._store.update(updated)
        return True

    def apply_profile(self, profile_id: str) -> bool:
        setting = self._store.get(profile_id)
        if setting is None:
            self.error_occurred.emit(f"Profile not found: {profile_id}")
            return False

        # 전환 전에 현재 활성 프로파일에 변경사항 자동 저장
        if self._active_profile_id and self._active_profile_id != profile_id:
            self.save_active_profile()

        GraphSettingMapper.to_app_state(setting, self._state)
        self._active_profile_id = profile_id
        self.profile_applied.emit(profile_id)
        return True

    def rename_profile(self, profile_id: str, new_name: str) -> bool:
        setting = self._store.get(profile_id)
        if setting is None:
            self.error_occurred.emit(f"Profile not found: {profile_id}")
            return False

        if setting.name == new_name:
            return True

        previous_name = setting.name
        updated = setting.with_name(new_name)
        self._store.update(updated)

        # Record undo via main stack
        if self._main_undo_stack:
            pid, old_n, new_n = profile_id, previous_name, new_name
            def _do_rename():
                s = self._store.get(pid)
                if s:
                    self._store.update(s.with_name(new_n))
                    self.profile_renamed.emit(pid, new_n)
            def _undo_rename():
                s = self._store.get(pid)
                if s:
                    self._store.update(s.with_name(old_n))
                    self.profile_renamed.emit(pid, old_n)
            self._main_undo_stack.record(UndoCommand(
                action_type=UndoActionType.PROFILE_RENAME,
                description=f"Rename profile '{previous_name}' → '{new_name}'",
                do=_do_rename,
                undo=_undo_rename,
            ))

        self.profile_renamed.emit(profile_id, new_name)
        return True

    def delete_profile(self, profile_id: str) -> bool:
        setting = self._store.get(profile_id)
        if setting is None:
            self.error_occurred.emit(f"Profile not found: {profile_id}")
            return False

        if not self._store.remove(profile_id):
            self.error_occurred.emit(f"Failed to delete profile: {profile_id}")
            return False

        # Record undo via main stack
        if self._main_undo_stack:
            deleted_setting = setting
            def _do_delete():
                self._store.remove(deleted_setting.id)
                self.profile_deleted.emit(deleted_setting.id)
            def _undo_delete():
                self._store.add(deleted_setting)
                self.profile_created.emit(deleted_setting.id)
            self._main_undo_stack.record(UndoCommand(
                action_type=UndoActionType.PROFILE_DELETE,
                description=f"Delete profile '{setting.name}'",
                do=_do_delete,
                undo=_undo_delete,
            ))

        if self._active_profile_id == profile_id:
            self._active_profile_id = None
        self.profile_deleted.emit(profile_id)
        return True

    def duplicate_profile(self, profile_id: str) -> Optional[str]:
        # 복제 전에 현재 활성 프로파일의 변경사항 자동 저장
        if self._active_profile_id:
            self.save_active_profile()

        setting = self._store.duplicate(profile_id)
        if setting is None:
            self.error_occurred.emit(f"Profile not found: {profile_id}")
            return None

        self.profile_created.emit(setting.id)
        return setting.id

    def export_profile(self, profile_id: str, path: str) -> bool:
        setting = self._store.get(profile_id)
        if setting is None:
            self.error_occurred.emit(f"Profile not found: {profile_id}")
            return False

        try:
            self._store.export_async(setting, path)
            return True
        except Exception as exc:  # pragma: no cover - defensive
            self.error_occurred.emit(str(exc))
            return False

    def import_profile(self, dataset_id: str, path: str) -> Optional[str]:
        try:
            imported = self._store.import_async(path)
            setting = imported.result() if hasattr(imported, "result") else imported
            if setting is None:
                raise ValueError("Import failed")

            if setting.dataset_id != dataset_id:
                setting = replace(setting, dataset_id=dataset_id)

            self._store.add(setting)
            self.profile_created.emit(setting.id)
            return setting.id
        except Exception as exc:
            self.error_occurred.emit(str(exc))
            return None

    def has_unsaved_changes(self) -> bool:
        if not self._active_profile_id:
            return False

        setting = self._store.get(self._active_profile_id)
        if setting is None:
            return False

        current = GraphSettingMapper.from_app_state(
            self._state,
            name=setting.name,
            dataset_id=setting.dataset_id,
        )
        return not self._settings_equal(setting, current)

    @property
    def active_profile_id(self) -> Optional[str]:
        """Currently active profile ID."""
        return self._active_profile_id

    @active_profile_id.setter
    def active_profile_id(self, value: Optional[str]) -> None:
        if self._active_profile_id != value:
            self._active_profile_id = value
            if value is not None:
                self.profile_applied.emit(value)

    def undo(self) -> bool:
        """Delegate to main undo stack. Kept for backward compatibility."""
        if self._main_undo_stack and self._main_undo_stack.can_undo():
            self._main_undo_stack.undo()
            return True
        return False

    @staticmethod
    def _settings_equal(a: GraphSetting, b: GraphSetting) -> bool:
        """Compare two GraphSettings for semantic equality.

        Compares all relevant fields including **all** chart_settings keys
        (using normalized defaults so missing keys are treated as defaults).
        """
        if a.chart_type != b.chart_type:
            return False
        if a.x_column != b.x_column:
            return False
        if tuple(a.group_columns) != tuple(b.group_columns):
            return False
        if tuple(a.value_columns) != tuple(b.value_columns):
            return False
        if tuple(a.hover_columns) != tuple(b.hover_columns):
            return False
        if tuple(a.filters) != tuple(b.filters):
            return False
        if tuple(a.sorts) != tuple(b.sorts):
            return False
        # Compare chart_settings: normalize with defaults so missing keys
        # are filled in, then compare all keys from both sides.
        if a.normalized_chart_settings() != b.normalized_chart_settings():
            return False
        return True
