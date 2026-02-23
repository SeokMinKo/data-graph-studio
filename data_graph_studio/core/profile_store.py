"""
ProfileStore - GraphSetting storage layer.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import replace
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)

from concurrent.futures import Future, ThreadPoolExecutor

from .profile import GraphSetting


class ProfileStore:
    def __init__(self):
        """Initialize an empty ProfileStore with no stored graph settings.

        Output: None
        Invariants: self._settings is always a dict mapping setting ID to GraphSetting
        """
        self._settings: Dict[str, GraphSetting] = {}

    def add(self, setting: GraphSetting) -> None:
        """Add a graph setting to the store, keyed by its ID.

        Input: setting — GraphSetting, the profile to store
        Output: None
        Invariants: any existing entry with the same ID is silently overwritten
        """
        logger.debug("profile_store.add", extra={"setting_id": setting.id, "profile_name": setting.name})
        self._settings[setting.id] = setting

    def get(self, setting_id: str) -> Optional[GraphSetting]:
        """Look up a graph setting by its unique ID.

        Input: setting_id — str, the profile ID to retrieve
        Output: GraphSetting | None — the stored setting, or None if not found
        """
        return self._settings.get(setting_id)

    def get_by_dataset(self, dataset_id: str) -> List[GraphSetting]:
        """Return all graph settings that belong to the specified dataset.

        Input: dataset_id — str, the dataset whose profiles are requested
        Output: List[GraphSetting] — all stored settings where setting.dataset_id == dataset_id;
                                      empty list when none match
        """
        return [s for s in self._settings.values() if s.dataset_id == dataset_id]

    def update(self, setting: GraphSetting) -> None:
        """Replace the stored graph setting for setting.id with the provided version.

        Input: setting — GraphSetting, the updated profile; must share an ID with an existing entry
        Output: None
        Invariants: if the ID does not exist the entry is created (same as add)
        """
        self._settings[setting.id] = setting

    def remove(self, setting_id: str) -> bool:
        """Remove a graph setting by ID and return whether it existed.

        Input: setting_id — str, ID of the profile to remove
        Output: bool — True when the setting was found and removed; False when not found
        """
        if setting_id in self._settings:
            del self._settings[setting_id]
            logger.debug("profile_store.remove", extra={"setting_id": setting_id})
            return True
        logger.warning("profile_store.remove.not_found", extra={"setting_id": setting_id})
        return False

    def duplicate(self, setting_id: str) -> Optional[GraphSetting]:
        """Create and store a copy of a graph setting with a new UUID and a conflict-free name.

        Input: setting_id — str, ID of the profile to duplicate
        Output: GraphSetting | None — the newly stored copy, or None if setting_id is not found
        Invariants: the duplicated setting has a unique ID and a name that does not collide
                    with any existing profile for the same dataset
        """
        setting = self.get(setting_id)
        if setting is None:
            return None

        new_name = self._resolve_name_conflict(setting.name, setting.dataset_id)
        new_setting = replace(
            setting,
            id=str(uuid.uuid4()),
            name=new_name,
            created_at=time.time(),
            modified_at=time.time(),
        )
        self.add(new_setting)
        return new_setting

    def export_async(self, setting: GraphSetting, path: str) -> Future:
        """Serialize a graph setting to JSON at path, running the write in a background thread.

        Input: setting — GraphSetting, the profile to serialize
               path — str, destination file path for the JSON output
        Output: Future — resolves to None when the write completes; may hold an OSError on failure
        """
        logger.debug("profile_store.export_async", extra={"setting_id": setting.id, "path": path})

        def _export():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(setting.to_dict(), f, ensure_ascii=False, indent=2)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_export)
        executor.shutdown(wait=False)
        return future

    def import_async(self, path: str) -> Future:
        """Load and deserialize a GraphSetting from a JSON file in a background thread.

        The returned Future resolves to the deserialized GraphSetting. The setting is NOT
        automatically added to the store; callers must call add() after the Future resolves.

        Input: path — str, source JSON file path previously written by export_async
        Output: Future — resolves to a GraphSetting on success; may hold an OSError or KeyError
                          on parse/read failure
        """
        logger.debug("profile_store.import_async", extra={"path": path})

        def _import() -> GraphSetting:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return GraphSetting.from_dict(data)

        executor = ThreadPoolExecutor(max_workers=1)
        future = executor.submit(_import)
        executor.shutdown(wait=False)
        return future

    def _resolve_name_conflict(self, name: str, dataset_id: str) -> str:
        existing = self._names_for_dataset(dataset_id)
        if name not in existing:
            return name

        counter = 1
        while f"{name} ({counter})" in existing:
            counter += 1
        return f"{name} ({counter})"

    def _names_for_dataset(self, dataset_id: str) -> Set[str]:
        return {s.name for s in self.get_by_dataset(dataset_id)}
