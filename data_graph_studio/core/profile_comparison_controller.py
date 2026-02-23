"""ProfileComparisonController — orchestrates profile comparison lifecycle."""

from __future__ import annotations

from typing import List, TYPE_CHECKING

from .observable import Observable
from .profile_store import ProfileStore
from .profile_controller import ProfileController
from .state import AppState, ComparisonMode

if TYPE_CHECKING:
    from .profile import GraphSetting


def _can_overlay(profiles: List["GraphSetting"]) -> bool:
    """Check if all profiles share the same x_column (UT-6).

    Mirrors ProfileOverlayRenderer.can_overlay but lives in core to avoid
    a UI-layer dependency.  Returns True only when there is at least one
    profile and every profile has the same non-None x_column.
    """
    if not profiles:
        return False
    x_cols = {p.x_column for p in profiles}
    return len(x_cols) == 1 and None not in x_cols


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
        """Initialize the controller and wire up profile lifecycle subscriptions.

        Input: store — ProfileStore, used to look up GraphSetting objects by ID
               controller — ProfileController, source of profile_deleted/profile_renamed events
               state — AppState, where comparison state is persisted
        Output: None
        Invariants: comparison is inactive at construction; controller events are subscribed
        """
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
        """Validate and activate a profile comparison, updating AppState and emitting events.

        Saves the currently active profile before proceeding. Validation checks:
        at least 2 profiles, all profiles exist and belong to the same dataset,
        OVERLAY/DIFFERENCE modes require a shared X column, DIFFERENCE requires exactly 2 profiles.

        Input: dataset_id — str, the dataset the profiles belong to
               profile_ids — List[str], IDs of profiles to compare (min 2)
               mode — ComparisonMode, requested comparison mode (default SIDE_BY_SIDE)
        Output: bool — True when comparison activated; False when any validation fails
        Invariants: on failure, comparison state is unchanged and error_occurred is emitted
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
            if not _can_overlay(settings):
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
        """Exit comparison mode, clearing all comparison state and emitting comparison_ended.

        Output: None
        Invariants: no-op when comparison is not currently active
        """
        if not self._active:
            return

        self._active = False
        self._current_mode = ComparisonMode.SINGLE
        self._profile_ids.clear()
        self._dataset_id = ""

        self._state.clear_profile_comparison()
        self.emit("comparison_ended")

    def change_mode(self, mode: ComparisonMode) -> bool:
        """Switch the comparison mode while a comparison is already active.

        Switching to SINGLE is equivalent to calling stop_comparison. OVERLAY/DIFFERENCE
        modes are validated against the current profile set.

        Input: mode — ComparisonMode, the new comparison mode to apply
        Output: bool — True when mode changed or comparison stopped; False when inactive
                       or validation fails
        Invariants: on failure, current mode is unchanged and error_occurred is emitted
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
            if not _can_overlay(settings):
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
        """Return True when a profile comparison session is currently active.

        Output: bool — True if start_comparison succeeded and stop_comparison has not been called
        """
        return self._active

    @property
    def current_profiles(self) -> List[str]:
        """Return a snapshot copy of the profile IDs currently in the comparison.

        Output: List[str] — copy of internal profile ID list; empty when not active
        """
        return list(self._profile_ids)

    @property
    def current_mode(self) -> ComparisonMode:
        """Return the currently active comparison mode.

        Output: ComparisonMode — SINGLE when no comparison is active, otherwise the mode set by
                                  start_comparison or change_mode
        """
        return self._current_mode

    @property
    def dataset_id(self) -> str:
        """Return the dataset ID associated with the current comparison.

        Output: str — dataset_id passed to start_comparison; empty string when not active
        """
        return self._dataset_id
