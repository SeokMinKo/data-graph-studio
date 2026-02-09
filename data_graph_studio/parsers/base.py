"""Base parser interface for custom file parsers."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

logger = logging.getLogger(__name__)


class ParserProfile:
    """A saved configuration preset for a parser.

    Attributes:
        name: Human-readable profile name.
        settings: Arbitrary dict of parser-specific settings.
    """

    def __init__(self, name: str, settings: Optional[Dict[str, Any]] = None):
        self.name = name
        self.settings: Dict[str, Any] = settings or {}

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "settings": self.settings}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ParserProfile":
        return cls(name=data["name"], settings=data.get("settings", {}))


class BaseParser(ABC):
    """Custom parser base class.

    Subclass this to add new parsers to the Parser menu.
    Each parser must define:
      - name: display name for the menu
      - key: unique identifier (used for profile storage)
      - file_filter: QFileDialog filter string
      - default_settings(): returns default settings dict
      - parse(): read the file and return a polars DataFrame
    """

    # Display name shown in the Parser menu
    name: str = "Base Parser"

    # Unique key for profile storage (e.g. "ftrace")
    key: str = "base"

    # File dialog filter string
    file_filter: str = "All Files (*)"

    def default_settings(self) -> Dict[str, Any]:
        """Return default parser settings. Override in subclass."""
        return {}

    @abstractmethod
    def parse(self, file_path: str, settings: Optional[Dict[str, Any]] = None) -> pl.DataFrame:
        """Parse the given file and return a polars DataFrame.

        Args:
            file_path: Absolute path to the file to parse.
            settings: Optional settings dict (from a profile).

        Returns:
            A polars DataFrame with the parsed data.

        Raises:
            ValueError: If the file cannot be parsed.
        """
        ...


class ParserProfileStore:
    """Persists parser profiles to a JSON file.

    Storage format:
    {
        "ftrace": [
            {"name": "Default", "settings": {...}},
            {"name": "Sched only", "settings": {...}}
        ],
        "another_parser": [...]
    }
    """

    def __init__(self, storage_path: Optional[str] = None):
        if storage_path is None:
            storage_path = str(
                Path.home() / ".data_graph_studio" / "parser_profiles.json"
            )
        self._path = Path(storage_path)
        self._data: Dict[str, List[Dict[str, Any]]] = {}
        self._load()

    def _load(self) -> None:
        if self._path.exists():
            try:
                self._data = json.loads(self._path.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning(f"Failed to load parser profiles: {e}")
                self._data = {}

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps(self._data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as e:
            logger.warning(f"Failed to save parser profiles: {e}")

    def list_profiles(self, parser_key: str) -> List[ParserProfile]:
        """Return all saved profiles for a parser."""
        raw = self._data.get(parser_key, [])
        return [ParserProfile.from_dict(d) for d in raw]

    def get_profile(self, parser_key: str, profile_name: str) -> Optional[ParserProfile]:
        """Get a specific profile by name."""
        for d in self._data.get(parser_key, []):
            if d["name"] == profile_name:
                return ParserProfile.from_dict(d)
        return None

    def save_profile(self, parser_key: str, profile: ParserProfile) -> None:
        """Save or update a profile."""
        profiles = self._data.setdefault(parser_key, [])
        # Update existing or append
        for i, d in enumerate(profiles):
            if d["name"] == profile.name:
                profiles[i] = profile.to_dict()
                self._save()
                return
        profiles.append(profile.to_dict())
        self._save()

    def delete_profile(self, parser_key: str, profile_name: str) -> bool:
        """Delete a profile by name. Returns True if found."""
        profiles = self._data.get(parser_key, [])
        for i, d in enumerate(profiles):
            if d["name"] == profile_name:
                profiles.pop(i)
                self._save()
                return True
        return False

    def rename_profile(self, parser_key: str, old_name: str, new_name: str) -> bool:
        """Rename a profile. Returns True if found."""
        for d in self._data.get(parser_key, []):
            if d["name"] == old_name:
                d["name"] = new_name
                self._save()
                return True
        return False
