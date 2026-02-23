"""
ViewSyncManager — shared view synchronization for dataset and profile comparison.

Extracted from SideBySideLayout to be reusable across comparison modes.
Panels are registered via duck typing (must implement set_view_range / set_selection).
No UI-specific panel classes are imported.
"""

from __future__ import annotations

import logging
import threading
import weakref
from typing import Any, Optional, Tuple

from data_graph_studio.core.observable import Observable

logger = logging.getLogger(__name__)


class ViewSyncManager(Observable):
    """
    View synchronization manager.

    Synchronizes view ranges (pan/zoom) and data-point selection across
    registered panels.  Uses a leading-edge throttle (max 1 sync per 50 ms)
    and a WeakValueDictionary so panels are auto-removed on destruction.

    Panels must implement:
        set_view_range(x_range, y_range, sync_x: bool, sync_y: bool)
        set_selection(indices: list)

    Events emitted:
        view_range_synced(source_id: str, x_range: list, y_range: list)
        selection_synced(source_id: str, selected_indices: list)
    """

    # Throttle interval in milliseconds
    THROTTLE_MS = 50

    def __init__(self) -> None:
        """Initialise the sync manager with default settings and empty panel registry.

        Output: None
        Invariants: sync_x is True, sync_y is False, sync_selection is True on creation;
                    _panels registry is empty; no timers are running
        """
        super().__init__()

        # --- public sync toggles ---
        self._sync_x: bool = True
        self._sync_y: bool = False
        self._sync_selection: bool = True

        # --- panel registry (weak refs) ---
        self._panels: weakref.WeakValueDictionary[str, Any] = (
            weakref.WeakValueDictionary()
        )

        # --- infinite-loop guard ---
        self._is_syncing: bool = False

        # --- threading lock for timer state ---
        self._lock = threading.Lock()

        # --- range throttle (leading edge) ---
        self._range_throttle_active: bool = False
        self._pending_range: Optional[Tuple[str, list, list]] = None
        self._range_timer: Optional[threading.Timer] = None

        # --- selection throttle (leading edge) ---
        self._sel_throttle_active: bool = False
        self._pending_selection: Optional[Tuple[str, list]] = None
        self._sel_timer: Optional[threading.Timer] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sync_x(self) -> bool:
        """Return True when X-axis range synchronisation is enabled.

        Output: bool — current value of the _sync_x flag
        """
        return self._sync_x

    @sync_x.setter
    def sync_x(self, value: bool) -> None:
        """Enable or disable X-axis range synchronisation.

        Input: value — bool; True enables X-axis sync across panels
        Output: None
        """
        self._sync_x = value

    @property
    def sync_y(self) -> bool:
        """Return True when Y-axis range synchronisation is enabled.

        Output: bool — current value of the _sync_y flag
        """
        return self._sync_y

    @sync_y.setter
    def sync_y(self, value: bool) -> None:
        """Enable or disable Y-axis range synchronisation.

        Input: value — bool; True enables Y-axis sync across panels
        Output: None
        """
        self._sync_y = value

    @property
    def sync_selection(self) -> bool:
        """Return True when selection synchronisation is enabled.

        Output: bool — current value of the _sync_selection flag
        """
        return self._sync_selection

    @sync_selection.setter
    def sync_selection(self, value: bool) -> None:
        """Enable or disable selection synchronisation across panels.

        Input: value — bool; True propagates data-point selection to all panels
        Output: None
        """
        self._sync_selection = value

    @property
    def panel_count(self) -> int:
        """Number of currently alive registered panels."""
        return len(self._panels)

    # ------------------------------------------------------------------
    # Panel registration
    # ------------------------------------------------------------------

    def register_panel(self, panel_id: str, panel: Any) -> None:
        """Register a panel for sync, replacing any existing panel with the same id.

        Input: panel_id — str, unique identifier for the panel
               panel — Any, panel object that implements set_view_range and set_selection
        Output: None
        Invariants: panel is held via weak reference and auto-removed when garbage-collected
        """
        self._panels[panel_id] = panel

    def unregister_panel(self, panel_id: str) -> None:
        """Explicitly remove a panel from the registry.

        Input: panel_id — str, the id of the panel to remove
        Output: None
        Invariants: no-op if panel_id is not found; never raises KeyError
        """
        try:
            del self._panels[panel_id]
        except KeyError:
            pass

    # ------------------------------------------------------------------
    # Range sync (with leading-edge throttle)
    # ------------------------------------------------------------------

    def on_source_range_changed(
        self,
        source_id: str,
        x_range: list,
        y_range: list,
    ) -> None:
        """Propagate a view range change from one panel to all others.

        Uses leading-edge throttle: the first event in each 50 ms window fires
        immediately; subsequent events in the window are queued and the last one
        fires when the window expires.

        Input: source_id — str, id of the panel that changed its range
               x_range — list, new X-axis range [min, max]
               y_range — list, new Y-axis range [min, max]
        Output: None
        Invariants: the source panel is never updated; sync_x and sync_y flags are respected
        """
        if self._is_syncing:
            return  # prevent infinite loop

        if not self._sync_x and not self._sync_y:
            return  # nothing to sync

        with self._lock:
            self._pending_range = (source_id, x_range, y_range)
            throttle_active = self._range_throttle_active
            if not throttle_active:
                self._range_throttle_active = True
        if not throttle_active:
            # Leading edge — fire immediately
            self._schedule_range_flush()
            with self._lock:
                pending = self._pending_range
                self._pending_range = None
            if pending is not None:
                src, xr, yr = pending
                self._dispatch_range(src, xr, yr)

    def _schedule_range_flush(self) -> None:
        """Start (or restart) the range throttle timer."""
        with self._lock:
            if self._range_timer is not None:
                self._range_timer.cancel()
            self._range_timer = threading.Timer(
                self.THROTTLE_MS / 1000.0, self._flush_pending_range
            )
            self._range_timer.daemon = True
            self._range_timer.start()

    def _flush_pending_range(self) -> None:
        """Timer callback: fire the pending range event if any."""
        with self._lock:
            self._range_timer = None
            self._range_throttle_active = False
            pending = self._pending_range
            self._pending_range = None
            if pending is not None:
                # Re-arm for the queued event before releasing the lock
                self._range_throttle_active = True
        if pending is not None:
            source_id, x_range, y_range = pending
            self._schedule_range_flush()
            self._dispatch_range(source_id, x_range, y_range)

    def _dispatch_range(
        self, source_id: str, x_range: list, y_range: list
    ) -> None:
        """Push range to all panels except the source."""
        self._is_syncing = True
        try:
            for pid, panel in list(self._panels.items()):
                if pid == source_id:
                    continue
                try:
                    panel.set_view_range(
                        x_range, y_range,
                        sync_x=self._sync_x,
                        sync_y=self._sync_y,
                    )
                except (AttributeError, RuntimeError, TypeError) as e:
                    logger.debug("view_sync.dispatch_range.panel_failed",
                                 extra={"panel_id": pid, "reason": type(e).__name__})
            self.emit("view_range_synced", source_id, list(x_range), list(y_range))
        finally:
            self._is_syncing = False

    # ------------------------------------------------------------------
    # Selection sync (with leading-edge throttle)
    # ------------------------------------------------------------------

    def on_source_selection_changed(
        self,
        source_id: str,
        indices: list,
    ) -> None:
        """Propagate a data-point selection change from one panel to all others.

        Uses leading-edge throttle identical to on_source_range_changed.

        Input: source_id — str, id of the panel whose selection changed
               indices — list, selected data-point indices
        Output: None
        Invariants: no-op when sync_selection is False; source panel is never updated
        """
        if self._is_syncing:
            return

        if not self._sync_selection:
            return

        with self._lock:
            self._pending_selection = (source_id, indices)
            throttle_active = self._sel_throttle_active
            if not throttle_active:
                self._sel_throttle_active = True
        if not throttle_active:
            self._schedule_sel_flush()
            with self._lock:
                pending = self._pending_selection
                self._pending_selection = None
            if pending is not None:
                src, idx = pending
                self._dispatch_selection(src, idx)

    def _schedule_sel_flush(self) -> None:
        """Start (or restart) the selection throttle timer."""
        with self._lock:
            if self._sel_timer is not None:
                self._sel_timer.cancel()
            self._sel_timer = threading.Timer(
                self.THROTTLE_MS / 1000.0, self._flush_pending_selection
            )
            self._sel_timer.daemon = True
            self._sel_timer.start()

    def _flush_pending_selection(self) -> None:
        """Timer callback: fire the pending selection event if any."""
        with self._lock:
            self._sel_timer = None
            self._sel_throttle_active = False
            pending = self._pending_selection
            self._pending_selection = None
            if pending is not None:
                # Re-arm for the queued event before releasing the lock
                self._sel_throttle_active = True
        if pending is not None:
            source_id, indices = pending
            self._schedule_sel_flush()
            self._dispatch_selection(source_id, indices)

    def _dispatch_selection(self, source_id: str, indices: list) -> None:
        """Push selection to all panels except the source."""
        self._is_syncing = True
        try:
            for pid, panel in list(self._panels.items()):
                if pid == source_id:
                    continue
                try:
                    panel.set_selection(indices)
                except (AttributeError, RuntimeError, TypeError) as e:
                    logger.debug("view_sync.dispatch_selection.panel_failed",
                                 extra={"panel_id": pid, "reason": type(e).__name__})
            self.emit("selection_synced", source_id, list(indices))
        finally:
            self._is_syncing = False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset_all_views(self) -> None:
        """Ask every registered panel to auto-fit its view range.

        Calls set_view_range(None, None, True, True) on each panel; None ranges
        signal "auto-fit" to the panel implementation.

        Output: None
        Invariants: all panels are called regardless of sync_x/sync_y settings;
                    panels that raise AttributeError, RuntimeError, or TypeError are silently skipped
        """
        self._is_syncing = True
        try:
            for panel in list(self._panels.values()):
                try:
                    panel.set_view_range(None, None, True, True)
                except (AttributeError, RuntimeError, TypeError) as e:
                    logger.debug("view_sync.reset_all_views.panel_failed",
                                 extra={"reason": type(e).__name__})
        finally:
            self._is_syncing = False

    def on_source_row_selection_changed(
        self,
        source_id: str,
        row_indices: list,
    ) -> None:
        """Propagate a rect/lasso row selection from one panel to all others.

        Bypasses sync_x/sync_y settings — row selection always propagates for visual
        consistency across panels.

        Input: source_id — str, id of the panel whose row selection changed
               row_indices — list, selected row indices
        Output: None
        Invariants: source panel is never updated; no throttling applied
        """
        if self._is_syncing:
            return

        self._is_syncing = True
        try:
            for pid, panel in list(self._panels.items()):
                if pid == source_id:
                    continue
                try:
                    panel.highlight_selection(row_indices)
                except (AttributeError, RuntimeError, TypeError) as e:
                    logger.debug("view_sync.row_selection.panel_failed",
                                 extra={"panel_id": pid, "reason": type(e).__name__})
        finally:
            self._is_syncing = False

    def clear(self) -> None:
        """Remove all panels and cancel any pending throttle timers.

        Output: None
        Invariants: panel_count is 0 after return; no background timers are running after return
        """
        self._panels.clear()
        with self._lock:
            self._pending_range = None
            self._pending_selection = None
            self._range_throttle_active = False
            self._sel_throttle_active = False
            if self._range_timer is not None:
                self._range_timer.cancel()
                self._range_timer = None
            if self._sel_timer is not None:
                self._sel_timer.cancel()
                self._sel_timer = None
