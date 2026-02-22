"""ProfileComparisonController — orchestrates profile comparison lifecycle."""

from __future__ import annotations

from typing import List, TYPE_CHECKING

from .observable import Observable
from .profile_store import ProfileStore
from .profile_controller import ProfileController
from .state import AppState, ComparisonMode

if TYPE_CHECKING:
    from .profile import GraphSetting


class ProfileComparisonController(Observable):
    """Orchestrates profile comparison lifecycle.

    Validates profile sets, manages comparison state, and responds to
    profile changes (delete / rename) during an active comparison.
    """

    def __init__(
        self,
        store: ProfileStore,
        controller: ProfileController,
        state: AppState,
    ):
        super().__init__()
        self._store = store
        self._controller = controller
        self._state = state

        self._active: bool = False
        self._current_mode: ComparisonMode = ComparisonMode.SINGLE
        self._profile_ids: List[str] = []
        self._dataset_id: str = ""

        # FR-10: react to profile lifecycle events
        controller.subscribe("profile_deleted", self._on_profile_deleted)
        controller.subscribe("profile_renamed", self._on_profile_renamed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start_comparison(
        self,
        dataset_id: str,
        profile_ids: List[str],
        mode: ComparisonMode = ComparisonMode.SIDE_BY_SIDE,
    ) -> bool:
        """Start a profile comparison.

        Returns ``False`` and emits ``error_occurred`` when validation fails.
        """
        # Save current active profile before comparing
        # (so chart_type and other changes are persisted)
        self._controller.save_active_profile()

        # --- validation ---
        if len(profile_ids) < 2:
            self.emit("error_occurred", "At least 2 profiles required for comparison")
            return False

        settings: List["GraphSetting"] = []
        for pid in profile_ids:
            s = self._store.get(pid)
            if s is None:
                self.emit("error_occurred", f"Profile not found: {pid}")
                return False
            settings.append(s)

        # All must belong to the same dataset
        ds_ids = {s.dataset_id for s in settings}
        if len(ds_ids) > 1:
            self.emit("error_occurred", "All profiles must belong to the same dataset")
            return False

        # Mode-specific validation
        if mode in (ComparisonMode.OVERLAY, ComparisonMode.DIFFERENCE):
            from ..ui.panels.profile_overlay import ProfileOverlayRenderer

            if not ProfileOverlayRenderer.can_overlay(settings):
                self.emit(
                    "error_occurred",
                    "All profiles must share the same X column for this mode",
                )
                return False

        if mode == ComparisonMode.DIFFERENCE and len(profile_ids) != 2:
            self.emit("error_occurred", "Difference mode requires exactly 2 profiles")
            return False

        # --- activate ---
        self._active = True
        self._current_mode = mode
        self._profile_ids = list(profile_ids)
        self._dataset_id = dataset_id

        # FR-8: set_profile_comparison auto-clears dataset comparison
        self._state.set_profile_comparison(dataset_id, profile_ids)

        # Set the requested mode on state (set_profile_comparison defaults to
        # SIDE_BY_SIDE if currently SINGLE; we may need to correct).
        if self._state._comparison_settings.mode != mode:
            self._state._comparison_settings.mode = mode
            self._state.emit("comparison_mode_changed", mode.value)
            self._state.emit("comparison_settings_changed")

        self.emit("comparison_started", mode.value, list(profile_ids))
        return True

    def stop_comparison(self) -> None:
        """FR-9: exit comparison mode."""
        if not self._active:
            return

        self._active = False
        self._current_mode = ComparisonMode.SINGLE
        self._profile_ids.clear()
        self._dataset_id = ""

        self._state.clear_profile_comparison()
        self.emit("comparison_ended")

    def change_mode(self, mode: ComparisonMode) -> bool:
        """Change comparison mode while active.

        Returns ``False`` and emits ``error_occurred`` on validation failure.
        """
        if not self._active:
            return False

        # Switching to SINGLE is equivalent to stopping
        if mode == ComparisonMode.SINGLE:
            self.stop_comparison()
            return True

        # Validate new mode against current profiles
        settings = [self._store.get(pid) for pid in self._profile_ids]
        settings = [s for s in settings if s is not None]

        if mode in (ComparisonMode.OVERLAY, ComparisonMode.DIFFERENCE):
            from ..ui.panels.profile_overlay import ProfileOverlayRenderer

            if not ProfileOverlayRenderer.can_overlay(settings):
                self.emit(
                    "error_occurred",
                    "All profiles must share the same X column for this mode",
                )
                return False

        if mode == ComparisonMode.DIFFERENCE and len(self._profile_ids) != 2:
            self.emit("error_occurred", "Difference mode requires exactly 2 profiles")
            return False

        self._current_mode = mode
        self._state._comparison_settings.mode = mode
        self._state.emit("comparison_mode_changed", mode.value)
        self._state.emit("comparison_settings_changed")

        self.emit("comparison_mode_changed", mode.value)
        return True

    # ------------------------------------------------------------------
    # ProfileController signal handlers (FR-10)
    # ------------------------------------------------------------------

    def _on_profile_deleted(self, profile_id: str) -> None:
        """FR-10: remove from comparison; exit if <2 remain."""
        if not self._active:
            return
        if profile_id not in self._profile_ids:
            return

        self._profile_ids.remove(profile_id)
        self.emit("panel_removed", profile_id)

        if len(self._profile_ids) < 2:
            self.stop_comparison()

    def _on_profile_renamed(self, profile_id: str, new_name: str) -> None:
        """FR-10: just forward — UI layers can listen to update headers."""
        # Nothing to do at the controller level; rename does not invalidate
        # the comparison.  UI widgets listen to ProfileController.profile_renamed
        # directly or to this controller's signals.
        pass

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def is_active(self) -> bool:
        return self._active

    @property
    def current_profiles(self) -> List[str]:
        return list(self._profile_ids)

    @property
    def current_mode(self) -> ComparisonMode:
        return self._current_mode

    @property
    def dataset_id(self) -> str:
        return self._dataset_id
