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


class ProfileController(QObject):
    profile_applied = Signal(str)
    profile_created = Signal(str)
    profile_deleted = Signal(str)
    profile_renamed = Signal(str, str)
    error_occurred = Signal(str)

    _UNDO_LIMIT = 10
    _UNDO_EXPIRY_SECONDS = 300

    def __init__(self, store: ProfileStore, state: AppState):
        super().__init__()
        self._store = store
        self._state = state
        self._active_profile_id: Optional[str] = None
        self._undo_stack: List[Dict[str, Any]] = []

    def create_profile(self, dataset_id: str, name: str) -> Optional[str]:
        try:
            setting = GraphSettingMapper.from_app_state(self._state, name=name, dataset_id=dataset_id)
            self._store.add(setting)
            self._active_profile_id = setting.id
            self.profile_created.emit(setting.id)
            return setting.id
        except Exception as exc:  # pragma: no cover - defensive
            self.error_occurred.emit(str(exc))
            return None

    def apply_profile(self, profile_id: str) -> bool:
        setting = self._store.get(profile_id)
        if setting is None:
            self.error_occurred.emit(f"Profile not found: {profile_id}")
            return False

        if self.has_unsaved_changes():
            self.error_occurred.emit("Unsaved changes")
            return False

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
        self._push_undo({"op": "rename", "profile_id": profile_id, "old_name": previous_name})
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

        self._push_undo({"op": "delete", "setting": setting})
        if self._active_profile_id == profile_id:
            self._active_profile_id = None
        self.profile_deleted.emit(profile_id)
        return True

    def duplicate_profile(self, profile_id: str) -> Optional[str]:
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

    def undo(self) -> bool:
        self._prune_undo_stack()
        while self._undo_stack:
            entry = self._undo_stack.pop()
            op = entry.get("op")
            if op == "delete":
                setting = entry.get("setting")
                if isinstance(setting, GraphSetting):
                    self._store.add(setting)
                    self.profile_created.emit(setting.id)
                    return True
            elif op == "rename":
                profile_id = entry.get("profile_id")
                old_name = entry.get("old_name")
                setting = self._store.get(profile_id)
                if setting is None:
                    continue
                restored = setting.with_name(old_name)
                self._store.update(restored)
                self.profile_renamed.emit(profile_id, old_name)
                return True
        return False

    def _push_undo(self, entry: Dict[str, Any]) -> None:
        entry["timestamp"] = time.time()
        self._undo_stack.append(entry)
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack = self._undo_stack[-self._UNDO_LIMIT :]

    def _prune_undo_stack(self) -> None:
        now = time.time()
        self._undo_stack = [
            entry
            for entry in self._undo_stack
            if now - entry.get("timestamp", 0) <= self._UNDO_EXPIRY_SECONDS
        ]

    @staticmethod
    def _settings_equal(a: GraphSetting, b: GraphSetting) -> bool:
        if a.chart_type != b.chart_type:
            return False
        if a.x_column != b.x_column:
            return False
        if tuple(a.group_columns) != tuple(b.group_columns):
            return False
        if tuple(a.value_columns) != tuple(b.value_columns):
            return False
        if list(a.hover_columns) != list(b.hover_columns):
            return False
        if list(a.filters) != list(b.filters):
            return False
        if list(a.sorts) != list(b.sorts):
            return False
        # Compare chart_settings: only compare keys present in both,
        # or treat empty dict as matching any defaults
        dict_a = dict(a.chart_settings) if a.chart_settings else {}
        dict_b = dict(b.chart_settings) if b.chart_settings else {}
        if dict_a and dict_b:
            # Compare only overlapping keys
            common_keys = set(dict_a.keys()) & set(dict_b.keys())
            for k in common_keys:
                if dict_a[k] != dict_b[k]:
                    return False
            # If one has keys the other doesn't, they still match
            # (extra keys from defaults are acceptable)
        return True
