"""
ToolbarManager - Central management for all toolbars.

Responsibilities:
  - Register/track all toolbars and their groups
  - Toolbar context menu (right-click)
  - Lock/unlock toolbar positions
  - Icon size management
  - State persistence via QSettings
  - View menu integration (toggle actions)
  - Group visibility and reordering
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING
from enum import Enum

from PySide6.QtWidgets import QToolBar, QMenu, QWidget, QLabel
from PySide6.QtCore import Qt, QObject, QSettings, QSize
from PySide6.QtGui import QAction, QActionGroup

if TYPE_CHECKING:
    from ..main_window import MainWindow

logger = logging.getLogger(__name__)


class IconSize(Enum):
    SMALL = 16
    MEDIUM = 24
    LARGE = 32


@dataclass
class ToolbarGroup:
    """Metadata for a logical group within a toolbar."""
    id: str                          # e.g. "main.file", "main.nav"
    label: str                       # e.g. "FILE", "NAV"
    toolbar_id: str                  # parent toolbar ID
    actions: List[QAction] = field(default_factory=list)
    widgets: List[QWidget] = field(default_factory=list)
    separator_action: Optional[QAction] = None  # trailing separator
    label_widget: Optional[QLabel] = None
    visible: bool = True
    order: int = 0


@dataclass
class ToolbarInfo:
    """Metadata for a registered toolbar."""
    id: str                          # "main", "secondary", "compare"
    toolbar: QToolBar
    display_name: str
    groups: List[ToolbarGroup] = field(default_factory=list)
    default_area: Qt.ToolBarArea = Qt.TopToolBarArea
    is_user_hideable: bool = True


class ToolbarManager(QObject):
    """Central toolbar manager for registration, context menus, and persistence."""

    SETTINGS_PREFIX = "toolbars"

    def __init__(self, main_window: MainWindow):
        super().__init__(main_window)
        self.w = main_window
        self._toolbars: Dict[str, ToolbarInfo] = {}
        self._locked = True
        self._global_icon_size = IconSize.SMALL
        self._settings = QSettings("Godol", "DataGraphStudio")
        self._lock_menu_action: Optional[QAction] = None

    # ------------------------------------------------------------------ #
    #  Registration API
    # ------------------------------------------------------------------ #

    def register_toolbar(
        self,
        toolbar_id: str,
        toolbar: QToolBar,
        display_name: str,
        area: Qt.ToolBarArea = Qt.TopToolBarArea,
        user_hideable: bool = True,
    ) -> ToolbarInfo:
        """Register a toolbar for management."""
        toolbar.setObjectName(f"toolbar_{toolbar_id}")
        info = ToolbarInfo(
            id=toolbar_id,
            toolbar=toolbar,
            display_name=display_name,
            default_area=area,
            is_user_hideable=user_hideable,
        )
        self._toolbars[toolbar_id] = info

        # Install context menu on this toolbar
        toolbar.setContextMenuPolicy(Qt.CustomContextMenu)
        toolbar.customContextMenuRequested.connect(
            lambda pos, tb=toolbar: self._show_context_menu(tb, pos)
        )
        return info

    def register_group(
        self,
        toolbar_id: str,
        group_id: str,
        label: str,
        actions: Optional[List] = None,
        widgets: Optional[List] = None,
        separator: Optional[QAction] = None,
        label_widget: Optional[QLabel] = None,
        order: int = 0,
    ) -> ToolbarGroup:
        """Register a logical group within a toolbar."""
        group = ToolbarGroup(
            id=group_id,
            label=label,
            toolbar_id=toolbar_id,
            actions=actions or [],
            widgets=widgets or [],
            separator_action=separator,
            label_widget=label_widget,
            order=order,
        )
        self._toolbars[toolbar_id].groups.append(group)
        return group

    # ------------------------------------------------------------------ #
    #  Context Menu
    # ------------------------------------------------------------------ #

    def _show_context_menu(self, toolbar: QToolBar, pos):
        menu = QMenu(toolbar)

        # Toolbar visibility toggles
        for info in self._toolbars.values():
            if not info.is_user_hideable:
                continue
            action = info.toolbar.toggleViewAction()
            action.setText(info.display_name)
            menu.addAction(action)

        menu.addSeparator()

        # Lock / Unlock
        lock_action = QAction(
            "Unlock Toolbars" if self._locked else "Lock Toolbars",
            menu,
        )
        lock_action.setCheckable(True)
        lock_action.setChecked(not self._locked)
        lock_action.triggered.connect(self._toggle_lock)
        menu.addAction(lock_action)

        # Icon Size submenu
        size_menu = menu.addMenu("Icon Size")
        size_group = QActionGroup(size_menu)
        for size in IconSize:
            a = QAction(f"{size.name.title()} ({size.value}px)", size_menu)
            a.setCheckable(True)
            a.setChecked(size == self._global_icon_size)
            a.triggered.connect(
                lambda checked, s=size: self._set_icon_size(s)
            )
            size_group.addAction(a)
            size_menu.addAction(a)

        menu.addSeparator()

        # Group visibility submenu
        groups_menu = menu.addMenu("Show Groups")
        for info in self._toolbars.values():
            for group in info.groups:
                ga = QAction(f"{group.label} ({info.display_name})", groups_menu)
                ga.setCheckable(True)
                ga.setChecked(group.visible)
                ga.triggered.connect(
                    lambda checked, gid=group.id: self.set_group_visible(gid, checked)
                )
                groups_menu.addAction(ga)

        menu.addSeparator()

        # Customize...
        customize_action = QAction("Customize Toolbars...", menu)
        customize_action.triggered.connect(self._open_customize_dialog)
        menu.addAction(customize_action)

        # Reset
        reset_action = QAction("Reset to Defaults", menu)
        reset_action.triggered.connect(self.reset_to_defaults)
        menu.addAction(reset_action)

        menu.exec(toolbar.mapToGlobal(pos))

    # ------------------------------------------------------------------ #
    #  Lock / Unlock
    # ------------------------------------------------------------------ #

    def _toggle_lock(self, unlocked: bool):
        self._locked = not unlocked
        for info in self._toolbars.values():
            info.toolbar.setMovable(not self._locked)
        if self._lock_menu_action is not None:
            self._lock_menu_action.setChecked(self._locked)
        self._save_state()

    @property
    def locked(self) -> bool:
        return self._locked

    # ------------------------------------------------------------------ #
    #  Icon Size
    # ------------------------------------------------------------------ #

    def _set_icon_size(self, size: IconSize):
        self._global_icon_size = size
        qsize = QSize(size.value, size.value)
        for info in self._toolbars.values():
            info.toolbar.setIconSize(qsize)
        self._save_state()

    # ------------------------------------------------------------------ #
    #  Group Visibility
    # ------------------------------------------------------------------ #

    def set_group_visible(self, group_id: str, visible: bool):
        """Show/hide all actions and widgets in a group."""
        for info in self._toolbars.values():
            for group in info.groups:
                if group.id == group_id:
                    group.visible = visible
                    if group.label_widget:
                        group.label_widget.setVisible(visible)
                    for action in group.actions:
                        action.setVisible(visible)
                    for widget in group.widgets:
                        widget.setVisible(visible)
                    if group.separator_action:
                        group.separator_action.setVisible(visible)
                    self._save_state()
                    return

    # ------------------------------------------------------------------ #
    #  Persistence
    # ------------------------------------------------------------------ #

    def _save_state(self):
        s = self._settings
        s.beginGroup(self.SETTINGS_PREFIX)

        # Qt native state (toolbar positions, areas, visibility)
        s.setValue("qt_state", self.w.saveState())

        s.setValue("locked", self._locked)
        s.setValue("icon_size", self._global_icon_size.value)

        # Group visibility and order
        for info in self._toolbars.values():
            for group in info.groups:
                s.setValue(f"group_visible/{group.id}", group.visible)
            order_ids = [g.id for g in sorted(info.groups, key=lambda g: g.order)]
            s.setValue(f"group_order/{info.id}", order_ids)

        s.endGroup()

    def restore_state(self):
        s = self._settings
        s.beginGroup(self.SETTINGS_PREFIX)

        # Locked
        self._locked = s.value("locked", True, type=bool)
        for info in self._toolbars.values():
            info.toolbar.setMovable(not self._locked)

        # Icon size
        icon_val = s.value("icon_size", 16, type=int)
        try:
            self._global_icon_size = IconSize(icon_val)
        except ValueError:
            self._global_icon_size = IconSize.SMALL
        qsize = QSize(self._global_icon_size.value, self._global_icon_size.value)
        for info in self._toolbars.values():
            info.toolbar.setIconSize(qsize)

        # Group visibility
        for info in self._toolbars.values():
            for group in info.groups:
                vis = s.value(f"group_visible/{group.id}", True, type=bool)
                if not vis:
                    self.set_group_visible(group.id, False)

        # Group order
        for info in self._toolbars.values():
            saved_order = s.value(f"group_order/{info.id}")
            if saved_order and isinstance(saved_order, list):
                for idx, gid in enumerate(saved_order):
                    for group in info.groups:
                        if group.id == gid:
                            group.order = idx
                            break
                # Rebuild if order differs from default
                self._rebuild_single_toolbar(info)

        # Qt native state (toolbar positions) — must be last
        qt_state = s.value("qt_state")
        if qt_state is not None:
            self.w.restoreState(qt_state)

        s.endGroup()

    # ------------------------------------------------------------------ #
    #  View Menu Integration
    # ------------------------------------------------------------------ #

    def populate_view_menu(self, view_menu: QMenu):
        """Add 'Toolbars' submenu to the View menu."""
        toolbar_menu = view_menu.addMenu("&Toolbars")

        for info in self._toolbars.values():
            if info.is_user_hideable:
                toggle = info.toolbar.toggleViewAction()
                toggle.setText(info.display_name)
                toolbar_menu.addAction(toggle)

        toolbar_menu.addSeparator()

        lock_action = QAction("Lock Toolbar Positions", toolbar_menu)
        lock_action.setCheckable(True)
        lock_action.setChecked(self._locked)
        lock_action.triggered.connect(
            lambda checked: self._toggle_lock(not checked)
        )
        toolbar_menu.addAction(lock_action)
        self._lock_menu_action = lock_action

        toolbar_menu.addSeparator()

        customize_action = QAction("Customize Toolbars...", toolbar_menu)
        customize_action.triggered.connect(self._open_customize_dialog)
        toolbar_menu.addAction(customize_action)

    # ------------------------------------------------------------------ #
    #  Customize Dialog
    # ------------------------------------------------------------------ #

    def _open_customize_dialog(self):
        from ..dialogs.toolbar_customize_dialog import ToolbarCustomizeDialog

        dialog = ToolbarCustomizeDialog(self, parent=self.w)
        if dialog.exec():
            self._apply_customization(dialog.get_result())

    def _apply_customization(self, result: dict):
        """Apply customization result from dialog."""
        for group_id, config in result.get("groups", {}).items():
            vis = config.get("visible")
            if vis is not None:
                self.set_group_visible(group_id, vis)
            order = config.get("order")
            if order is not None:
                for info in self._toolbars.values():
                    for group in info.groups:
                        if group.id == group_id:
                            group.order = order

        # Rebuild toolbar contents in new order
        for info in self._toolbars.values():
            self._rebuild_single_toolbar(info)
        self._save_state()

    # ------------------------------------------------------------------ #
    #  Toolbar Rebuild (reorder groups)
    # ------------------------------------------------------------------ #

    def _rebuild_single_toolbar(self, info: ToolbarInfo):
        """Rebuild a single toolbar's action order based on group.order values."""
        sorted_groups = sorted(info.groups, key=lambda g: g.order)
        toolbar = info.toolbar

        # Remove all actions/widgets
        toolbar.clear()

        for group in sorted_groups:
            if group.label_widget:
                toolbar.addWidget(group.label_widget)
                group.label_widget.setVisible(group.visible)

            for item in group.actions:
                if isinstance(item, QAction):
                    toolbar.addAction(item)
                    item.setVisible(group.visible)

            for widget in group.widgets:
                toolbar.addWidget(widget)
                widget.setVisible(group.visible)

            # Re-add separator
            if group.separator_action is not None:
                group.separator_action = toolbar.addSeparator()
                group.separator_action.setVisible(group.visible)

    def _rebuild_toolbars(self):
        """Rebuild all toolbars."""
        for info in self._toolbars.values():
            self._rebuild_single_toolbar(info)

    # ------------------------------------------------------------------ #
    #  Reset
    # ------------------------------------------------------------------ #

    def reset_to_defaults(self):
        """Reset all toolbar settings to defaults."""
        self._locked = True
        self._global_icon_size = IconSize.SMALL
        qsize = QSize(16, 16)
        for info in self._toolbars.values():
            info.toolbar.setMovable(False)
            info.toolbar.setIconSize(qsize)
            for idx, group in enumerate(info.groups):
                group.visible = True
                group.order = idx
        self._rebuild_toolbars()
        # Clear persisted state
        self._settings.beginGroup(self.SETTINGS_PREFIX)
        self._settings.remove("")
        self._settings.endGroup()
        if self._lock_menu_action is not None:
            self._lock_menu_action.setChecked(True)
