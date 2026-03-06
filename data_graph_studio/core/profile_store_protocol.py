"""ProfileStoreProtocol — typed interface for profile stores.

Issue #4 — replaces duck-typing hasattr chains in ProfileModel.
"""

from __future__ import annotations

from typing import List, Optional, Protocol, runtime_checkable

from .profile import GraphSetting


@runtime_checkable
class ProfileStoreProtocol(Protocol):
    """Minimal interface that ProfileModel requires from a store."""

    def get_by_dataset(self, dataset_id: str) -> List[GraphSetting]: ...

    def get(self, profile_id: str) -> Optional[GraphSetting]: ...

    def add(self, setting: GraphSetting) -> None: ...

    def update(self, setting: GraphSetting) -> None: ...

    def reorder(self, dataset_id: str, ids: List[str]) -> None: ...
