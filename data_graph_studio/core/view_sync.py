"""
ViewSyncManager — shared view synchronization for dataset and profile comparison.

Extracted from SideBySideLayout to be reusable across comparison modes.
Panels are registered via duck typing (must implement set_view_range / set_selection).
No UI-specific panel classes are imported.
"""

from __future__ import annotations

import weakref
from typing import Optional, Tuple

from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget


class ViewSyncManager(QObject):
    """
    View synchronization manager.

    Synchronizes view ranges (pan/zoom) and data-point selection across
    registered panels.  Uses a leading-edge throttle (max 1 sync per 50 ms)
    and a WeakValueDictionary so panels are auto-removed on destruction.

    Panels must implement:
        set_view_range(x_range, y_range, sync_x: bool, sync_y: bool)
        set_selection(indices: list)
    """

    # Signals emitted after a sync is dispatched
    view_range_synced = Signal(str, list, list)  # source_id, x_range, y_range
    selection_synced = Signal(str, list)  # source_id, selected_indices

    # Throttle interval in milliseconds
    THROTTLE_MS = 50

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)

        # --- public sync toggles ---
        self._sync_x: bool = True
        self._sync_y: bool = False
        self._sync_selection: bool = True

        # --- panel registry (weak refs) ---
        self._panels: weakref.WeakValueDictionary[str, QWidget] = (
            weakref.WeakValueDictionary()
        )

        # --- infinite-loop guard ---
        self._is_syncing: bool = False

        # --- range throttle (leading edge) ---
        self._range_throttle_timer = QTimer(self)
        self._range_throttle_timer.setSingleShot(True)
        self._range_throttle_timer.setInterval(self.THROTTLE_MS)
        self._range_throttle_timer.timeout.connect(self._flush_pending_range)
        self._range_throttle_active: bool = False
        self._pending_range: Optional[Tuple[str, list, list]] = None

        # --- selection throttle (leading edge) ---
        self._sel_throttle_timer = QTimer(self)
        self._sel_throttle_timer.setSingleShot(True)
        self._sel_throttle_timer.setInterval(self.THROTTLE_MS)
        self._sel_throttle_timer.timeout.connect(self._flush_pending_selection)
        self._sel_throttle_active: bool = False
        self._pending_selection: Optional[Tuple[str, list]] = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def sync_x(self) -> bool:
        return self._sync_x

    @sync_x.setter
    def sync_x(self, value: bool) -> None:
        self._sync_x = value

    @property
    def sync_y(self) -> bool:
        return self._sync_y

    @sync_y.setter
    def sync_y(self, value: bool) -> None:
        self._sync_y = value

    @property
    def sync_selection(self) -> bool:
        return self._sync_selection

    @sync_selection.setter
    def sync_selection(self, value: bool) -> None:
        self._sync_selection = value

    @property
    def panel_count(self) -> int:
        """Number of currently alive registered panels."""
        return len(self._panels)

    # ------------------------------------------------------------------
    # Panel registration
    # ------------------------------------------------------------------

    def register_panel(self, panel_id: str, panel: QWidget) -> None:
        """Register a panel for sync.  Replaces existing panel with same id."""
        self._panels[panel_id] = panel

    def unregister_panel(self, panel_id: str) -> None:
        """Explicitly remove a panel.  No-op if not found."""
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
        """
        Called when a panel's view range changes.

        Uses leading-edge throttle: the *first* event in a window fires
        immediately; subsequent events within the window are queued and
        the *last* one fires when the window expires.
        """
        if self._is_syncing:
            return  # prevent infinite loop

        if not self._sync_x and not self._sync_y:
            return  # nothing to sync

        if not self._range_throttle_active:
            # Leading edge — fire immediately
            self._range_throttle_active = True
            self._range_throttle_timer.start()
            self._dispatch_range(source_id, x_range, y_range)
        else:
            # Within throttle window — store as pending (last-write-wins)
            self._pending_range = (source_id, x_range, y_range)

    def _flush_pending_range(self) -> None:
        """Timer callback: fire the pending range event if any."""
        self._range_throttle_active = False
        if self._pending_range is not None:
            source_id, x_range, y_range = self._pending_range
            self._pending_range = None
            # This may re-arm the throttle via on_source_range_changed path,
            # but we call _dispatch_range directly to avoid double-guard issues.
            self._range_throttle_active = True
            self._range_throttle_timer.start()
            self._dispatch_range(source_id, x_range, y_range)

    def _dispatch_range(self, source_id: str, x_range: list, y_range: list) -> None:
        """Push range to all panels except the source."""
        self._is_syncing = True
        try:
            for pid, panel in list(self._panels.items()):
                if pid == source_id:
                    continue
                try:
                    panel.set_view_range(
                        x_range,
                        y_range,
                        sync_x=self._sync_x,
                        sync_y=self._sync_y,
                    )
                except Exception:
                    pass  # panel may have been partially destroyed
            self.view_range_synced.emit(source_id, list(x_range), list(y_range))
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
        """Called when a panel's data-point selection changes."""
        if self._is_syncing:
            return

        if not self._sync_selection:
            return

        if not self._sel_throttle_active:
            self._sel_throttle_active = True
            self._sel_throttle_timer.start()
            self._dispatch_selection(source_id, indices)
        else:
            self._pending_selection = (source_id, indices)

    def _flush_pending_selection(self) -> None:
        """Timer callback: fire the pending selection event if any."""
        self._sel_throttle_active = False
        if self._pending_selection is not None:
            source_id, indices = self._pending_selection
            self._pending_selection = None
            self._sel_throttle_active = True
            self._sel_throttle_timer.start()
            self._dispatch_selection(source_id, indices)

    def _dispatch_selection(self, source_id: str, indices: list) -> None:
        """Push selection to all panels except the source.

        If panel.set_selection supports source tagging, pass source_id to prevent
        panel-local feedback loops.
        """
        self._is_syncing = True
        try:
            for pid, panel in list(self._panels.items()):
                if pid == source_id:
                    continue
                try:
                    panel.set_selection(indices, source_id=source_id)
                except TypeError:
                    # Backward compatibility for legacy panel API
                    try:
                        panel.set_selection(indices)
                    except Exception:
                        pass
                except Exception:
                    pass
            self.selection_synced.emit(source_id, list(indices))
        finally:
            self._is_syncing = False

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def reset_all_views(self) -> None:
        """
        Ask every panel to reset to auto-range.

        Calls ``set_view_range(None, None, True, True)`` — panels should
        interpret ``None`` ranges as "auto-fit".
        """
        self._is_syncing = True
        try:
            for panel in list(self._panels.values()):
                try:
                    panel.set_view_range(None, None, True, True)
                except Exception:
                    pass
        finally:
            self._is_syncing = False

    def on_source_row_selection_changed(
        self,
        source_id: str,
        row_indices: list,
    ) -> None:
        """Called when a panel's row selection (rect/lasso) changes.

        Always syncs regardless of sync_x/sync_y settings — row selection
        is always propagated for visual consistency.
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
                except Exception:
                    pass
        finally:
            self._is_syncing = False

    def clear(self) -> None:
        """Remove all panels and cancel pending timers."""
        self._panels.clear()
        self._pending_range = None
        self._pending_selection = None
        self._range_throttle_active = False
        self._sel_throttle_active = False
        if self._range_throttle_timer.isActive():
            self._range_throttle_timer.stop()
        if self._sel_throttle_timer.isActive():
            self._sel_throttle_timer.stop()
