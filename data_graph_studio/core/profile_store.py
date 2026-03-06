"""
ProfileStore - GraphSetting storage layer.

Single source of truth for all profile/GraphSetting data.
Supports optional JSON-file persistence via save_to_disk / load_from_disk.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Dict, List, Optional, Set

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

logger = logging.getLogger(__name__)


def _safe_trash(path: str) -> None:
    """Move file to trash; fall back to os.remove if send2trash unavailable."""
    try:
        from send2trash import send2trash  # type: ignore

        send2trash(path)
    except ImportError:
        logger.info("send2trash not installed, using os.remove for %s", path)
        os.remove(path)


class ProfileStore:
    def __init__(self):
        self._settings: Dict[str, GraphSetting] = {}
        self._persist_dir: Optional[Path] = None

    def add(self, setting: GraphSetting) -> None:
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
            return True
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

    # ==================== Persistence ====================

    def set_persist_dir(self, directory: Path) -> None:
        """Set directory for JSON persistence (e.g. ~/.dgs/profiles/{dataset_hash}/)."""
        self._persist_dir = Path(directory)
        self._persist_dir.mkdir(parents=True, exist_ok=True)

    def save_to_disk(self) -> None:
        """Save all settings to individual JSON files in persist_dir."""
        if self._persist_dir is None:
            return
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        # Write current settings
        written_ids: set[str] = set()
        for setting_id, setting in self._settings.items():
            path = self._persist_dir / f"{setting_id}.json"
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(setting.to_dict(), f, ensure_ascii=False, indent=2)
                written_ids.add(setting_id)
            except Exception as e:
                logger.warning("Failed to save profile %s: %s", setting_id, e)
        # Remove stale files
        for existing in self._persist_dir.glob("*.json"):
            if existing.stem not in written_ids:
                try:
                    _safe_trash(str(existing))
                except Exception as e:
                    logger.warning(
                        "Failed to remove stale profile file %s: %s", existing, e
                    )

    def load_from_disk(self) -> int:
        """Load all settings from persist_dir. Returns count loaded."""
        if self._persist_dir is None or not self._persist_dir.exists():
            return 0
        count = 0
        for path in self._persist_dir.glob("*.json"):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                setting = GraphSetting.from_dict(data)
                self._settings[setting.id] = setting
                count += 1
            except Exception as e:
                logger.warning("Failed to load profile from %s: %s", path, e)
        return count

    def delete_file(self, setting_id: str) -> None:
        """Delete the persisted file for a setting (using trash)."""
        if self._persist_dir is None:
            return
        path = self._persist_dir / f"{setting_id}.json"
        if path.exists():
            try:
                _safe_trash(str(path))
            except Exception as e:
                logger.warning("Failed to trash profile file %s: %s", path, e)
