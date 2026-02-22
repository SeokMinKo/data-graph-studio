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

try:
    from PySide6.QtConcurrent import run as qt_run
    from PySide6.QtCore import QFuture
except Exception:  # pragma: no cover - fallback for non-Qt environments
    qt_run = None
    QFuture = None

try:  # pragma: no cover - fallback when Qt unavailable
    from concurrent.futures import ThreadPoolExecutor
except Exception:  # pragma: no cover
    ThreadPoolExecutor = None

from .profile import GraphSetting


class ProfileStore:
    def __init__(self):
        self._settings: Dict[str, GraphSetting] = {}

    def add(self, setting: GraphSetting) -> None:
        logger.debug("profile_store.add", extra={"setting_id": setting.id, "name": setting.name})
        self._settings[setting.id] = setting

    def get(self, setting_id: str) -> Optional[GraphSetting]:
        return self._settings.get(setting_id)

    def get_by_dataset(self, dataset_id: str) -> List[GraphSetting]:
        return [s for s in self._settings.values() if s.dataset_id == dataset_id]

    def update(self, setting: GraphSetting) -> None:
        self._settings[setting.id] = setting

    def remove(self, setting_id: str) -> bool:
        if setting_id in self._settings:
            del self._settings[setting_id]
            logger.debug("profile_store.remove", extra={"setting_id": setting_id})
            return True
        logger.warning("profile_store.remove.not_found", extra={"setting_id": setting_id})
        return False

    def duplicate(self, setting_id: str) -> Optional[GraphSetting]:
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

    def export_async(self, setting: GraphSetting, path: str) -> None:
        logger.debug("profile_store.export_async", extra={"setting_id": setting.id, "path": path})

        def _export():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(setting.to_dict(), f, ensure_ascii=False, indent=2)

        if qt_run is not None:
            qt_run(_export)
            return

        if ThreadPoolExecutor is None:
            _export()
            return

        executor = ThreadPoolExecutor(max_workers=1)
        executor.submit(_export)
        executor.shutdown(wait=False)

    def import_async(self, path: str) -> "QFuture":
        logger.debug("profile_store.import_async", extra={"path": path})

        def _import() -> GraphSetting:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return GraphSetting.from_dict(data)

        if qt_run is not None:
            return qt_run(_import)

        if ThreadPoolExecutor is None:
            return _import()

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
