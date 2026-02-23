"""ProfileController - orchestrates GraphSetting operations."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

from .graph_setting_mapper import GraphSettingMapper
from .observable import Observable
from .profile import GraphSetting
from .profile_store import ProfileStore
from .state import AppState
from .exceptions import ConfigError


class ProfileController(Observable):
    """Orchestrates GraphSetting profile CRUD, undo, and AppState synchronization.

    Emits events: profile_created, profile_applied, profile_renamed,
    profile_deleted, error_occurred.  Maintains a bounded undo stack
    (max 10 entries, 5-minute expiry) for rename and delete operations.
    """

    _UNDO_LIMIT = 10          # max undo entries kept per session
    _UNDO_EXPIRY_SECONDS = 300  # 5 minutes: entries older than this are pruned on undo

    def __init__(self, store: ProfileStore, state: AppState):
        """Initialize the controller with a profile store and shared application state.

        Input: store — ProfileStore, persistent profile backend
               state — AppState, shared mutable application state
        Invariants: _active_profile_id starts None; undo stack starts empty
        """
        super().__init__()
        self._store = store
        self._state = state
        self._active_profile_id: Optional[str] = None
        self._undo_stack: List[Dict[str, Any]] = []

    def create_profile(self, dataset_id: str, name: str) -> Optional[str]:
        """Create a new graph setting profile for a dataset and return its ID.

        Input: dataset_id — str, the dataset this profile belongs to
               name — str, human-readable profile name
        Output: str | None — UUID string of the new profile, or None on error
        Raises: emits "error_occurred" event instead of propagating exceptions
        Invariants: auto-saves the previously active profile before creating;
                    new profile is activated and its defaults applied to AppState
        """
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
            self.emit("profile_created", setting.id)
            return setting.id
        except ConfigError as exc:  # pragma: no cover - defensive
            self.emit("error_occurred", str(exc))
            return None
        except (TypeError, AttributeError, ValueError) as exc:  # pragma: no cover - defensive
            self.emit("error_occurred", str(exc))
            return None

    def save_active_profile(self) -> bool:
        """Snapshot the current AppState into the active profile (auto-save).

        Output: bool — True if saved, False if no active profile or profile not found
        Invariants: preserves original id and created_at; updates modified_at to now
        """
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
        """Load a profile by ID and apply it to the current AppState.

        Input: profile_id — str, UUID of the profile to activate
        Output: bool — True on success, False if profile not found
        Invariants: auto-saves the previously active profile before switching;
                    emits "profile_applied" on success, "error_occurred" on failure
        """
        setting = self._store.get(profile_id)
        if setting is None:
            self.emit("error_occurred", f"Profile not found: {profile_id}")
            return False

        # 전환 전에 현재 활성 프로파일에 변경사항 자동 저장
        if self._active_profile_id and self._active_profile_id != profile_id:
            self.save_active_profile()

        GraphSettingMapper.to_app_state(setting, self._state)
        self._active_profile_id = profile_id
        self.emit("profile_applied", profile_id)
        return True

    def rename_profile(self, profile_id: str, new_name: str) -> bool:
        """Rename an existing profile and push the change onto the undo stack.

        Input: profile_id — str, UUID of the profile to rename
               new_name — str, desired new name
        Output: bool — True on success or if name is unchanged; False if not found
        Invariants: undo stack receives {"op": "rename", ...} entry;
                    emits "profile_renamed" on success, "error_occurred" on failure
        """
        setting = self._store.get(profile_id)
        if setting is None:
            self.emit("error_occurred", f"Profile not found: {profile_id}")
            return False

        if setting.name == new_name:
            return True

        previous_name = setting.name
        updated = setting.with_name(new_name)
        self._store.update(updated)
        self._push_undo({"op": "rename", "profile_id": profile_id, "old_name": previous_name})
        self.emit("profile_renamed", profile_id, new_name)
        return True

    def delete_profile(self, profile_id: str) -> bool:
        """Delete a profile from the store and record it for undo.

        Input: profile_id — str, UUID of the profile to delete
        Output: bool — True on success, False if not found or store removal failed
        Invariants: undo stack receives {"op": "delete", "setting": ...} entry;
                    _active_profile_id cleared if it matches the deleted profile;
                    emits "profile_deleted" on success, "error_occurred" on failure
        """
        setting = self._store.get(profile_id)
        if setting is None:
            self.emit("error_occurred", f"Profile not found: {profile_id}")
            return False

        if not self._store.remove(profile_id):
            self.emit("error_occurred", f"Failed to delete profile: {profile_id}")
            return False

        self._push_undo({"op": "delete", "setting": setting})
        if self._active_profile_id == profile_id:
            self._active_profile_id = None
        self.emit("profile_deleted", profile_id)
        return True

    def duplicate_profile(self, profile_id: str) -> Optional[str]:
        """Duplicate a profile and return the new profile's ID.

        Input: profile_id — str, UUID of the source profile to copy
        Output: str | None — UUID of the new duplicate profile, or None if not found
        Invariants: auto-saves the active profile before duplicating;
                    emits "profile_created" with the new ID on success
        """
        # 복제 전에 현재 활성 프로파일의 변경사항 자동 저장
        if self._active_profile_id:
            self.save_active_profile()

        setting = self._store.duplicate(profile_id)
        if setting is None:
            self.emit("error_occurred", f"Profile not found: {profile_id}")
            return None

        self.emit("profile_created", setting.id)
        return setting.id

    def export_profile(self, profile_id: str, path: str) -> bool:
        """Export a profile to a JSON file at the given path.

        Input: profile_id — str, UUID of the profile to export
               path — str, destination file path (must be writable)
        Output: bool — True on success, False if not found or write fails
        Raises: emits "error_occurred" instead of propagating ConfigError/RuntimeError
        """
        setting = self._store.get(profile_id)
        if setting is None:
            self.emit("error_occurred", f"Profile not found: {profile_id}")
            return False

        try:
            self._store.export_async(setting, path)
            return True
        except ConfigError as exc:  # pragma: no cover - defensive
            self.emit("error_occurred", str(exc))
            return False
        except (RuntimeError, TypeError) as exc:  # pragma: no cover - defensive
            self.emit("error_occurred", str(exc))
            return False

    def import_profile(self, dataset_id: str, path: str) -> Optional[str]:
        """Import a profile from a JSON file and associate it with the given dataset.

        Input: dataset_id — str, dataset to bind the imported profile to
               path — str, source JSON file path (must be readable)
        Output: str | None — UUID of the imported profile, or None on failure
        Raises: emits "error_occurred" on OSError, JSONDecodeError, ValueError, ConfigError
        Invariants: if the imported profile's dataset_id differs, it is overridden with dataset_id;
                    emits "profile_created" on success
        """
        try:
            imported = self._store.import_async(path)
            setting = imported.result() if hasattr(imported, "result") else imported
            if setting is None:
                raise ValueError("Import failed")

            if setting.dataset_id != dataset_id:
                setting = replace(setting, dataset_id=dataset_id)

            self._store.add(setting)
            self.emit("profile_created", setting.id)
            return setting.id
        except ConfigError as exc:
            self.emit("error_occurred", str(exc))
            return None
        except (OSError, json.JSONDecodeError, ValueError, TypeError) as exc:
            logger.error("profile_controller.import_profile.failed", exc_info=True)
            self.emit("error_occurred", str(exc))
            return None

    def has_unsaved_changes(self) -> bool:
        """Return True if the current AppState differs from the active saved profile.

        Output: bool — False if no active profile or profile not found;
                       True if any tracked field in AppState diverges from the stored profile
        Invariants: comparison ignores extra keys in chart_settings that only one side has
        """
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
        """Undo the last profile rename or delete operation.

        Output: bool — True if an operation was undone, False if the stack was empty
                       or all remaining entries were expired
        Invariants: prunes expired entries before attempting undo;
                    emits "profile_created" on delete-undo, "profile_renamed" on rename-undo
        """
        self._prune_undo_stack()
        while self._undo_stack:
            entry = self._undo_stack.pop()
            op = entry.get("op")
            if op == "delete":
                setting = entry.get("setting")
                if isinstance(setting, GraphSetting):
                    self._store.add(setting)
                    self.emit("profile_created", setting.id)
                    return True
            elif op == "rename":
                profile_id = entry.get("profile_id")
                old_name = entry.get("old_name")
                setting = self._store.get(profile_id)
                if setting is None:
                    continue
                restored = setting.with_name(old_name)
                self._store.update(restored)
                self.emit("profile_renamed", profile_id, old_name)
                return True
        return False

    def _push_undo(self, entry: Dict[str, Any]) -> None:
        """Append a timestamped entry to the undo stack, capping at _UNDO_LIMIT.

        Input: entry — Dict[str, Any], operation record with at least an "op" key
        Invariants: entry["timestamp"] set to current time; oldest entries dropped if > limit
        """
        entry["timestamp"] = time.time()
        self._undo_stack.append(entry)
        if len(self._undo_stack) > self._UNDO_LIMIT:
            self._undo_stack = self._undo_stack[-self._UNDO_LIMIT :]

    def _prune_undo_stack(self) -> None:
        """Remove undo entries older than _UNDO_EXPIRY_SECONDS.

        Invariants: entries without a "timestamp" key are treated as expired and removed
        """
        now = time.time()
        self._undo_stack = [
            entry
            for entry in self._undo_stack
            if now - entry.get("timestamp", 0) <= self._UNDO_EXPIRY_SECONDS
        ]

    @staticmethod
    def _settings_equal(a: GraphSetting, b: GraphSetting) -> bool:
        """Compare two GraphSettings for logical equality, ignoring non-overlapping chart_settings keys.

        Input: a, b — GraphSetting instances to compare
        Output: bool — True if all tracked fields match
        Invariants: chart_settings comparison only checks keys present in both dicts;
                    extra keys on either side do not cause inequality
        """
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
