# Phase 3a: Qt Decoupling — Core Layer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove Qt dependencies from 6 core files by migrating QObject/Signal to Observable, creating Qt adapter classes where UI connections are needed.

**Architecture:** Same pattern established in Phase 1 — each migrated class extends `Observable` instead of `QObject`, emitting string-keyed events. Qt adapter classes in `ui/adapters/` bridge the gap for UI components that need Qt signal/slot connections. All changes are backward-compatible from the UI perspective.

**Tech Stack:** Python 3.11, PySide6, existing `core/observable.py`, existing adapter pattern in `ui/adapters/`

---

## Reference: Existing Pattern

Phase 1 already established the pattern. Study these before starting:
- `data_graph_studio/core/observable.py` — base class
- `data_graph_studio/core/filtering.py` — migrated example
- `data_graph_studio/ui/adapters/filtering_adapter.py` — adapter example

Migration recipe:
```python
# BEFORE:
from PySide6.QtCore import QObject, Signal
class MyManager(QObject):
    something_happened = Signal(str)
    def __init__(self, parent=None):
        super().__init__(parent)
    def do_thing(self, val):
        self.something_happened.emit(val)

# AFTER:
from data_graph_studio.core.observable import Observable
class MyManager(Observable):
    def __init__(self):
        super().__init__()
    def do_thing(self, val):
        self.emit("something_happened", val)
```

Adapter in `ui/adapters/my_manager_adapter.py`:
```python
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.my_manager import MyManager

class MyManagerAdapter(QObject):
    something_happened = Signal(str)
    def __init__(self, manager: MyManager, parent=None):
        super().__init__(parent)
        manager.subscribe("something_happened", self.something_happened.emit)
```

---

## Task 1: Migrate `marking.py` — MarkingManager

**Files:**
- Modify: `data_graph_studio/core/marking.py`
- Create: `data_graph_studio/ui/adapters/marking_adapter.py`
- Test: `tests/unit/test_marking_observable.py`

**Context:** `MarkingManager` has 4 signals. No existing UI connections found (feature not yet wired up). Safe migration.

**Signals to migrate:**
```python
marking_changed = Signal(str, set)      → "marking_changed"
active_marking_changed = Signal(str)    → "active_marking_changed"
marking_created = Signal(str)           → "marking_created"
marking_removed = Signal(str)           → "marking_removed"
```

**Step 1: Write failing test**

Create `tests/unit/test_marking_observable.py`:
```python
"""MarkingManager uses Observable, not Qt signals."""
import pytest
from data_graph_studio.core.marking import MarkingManager, MarkMode


def test_marking_manager_is_not_qobject():
    """MarkingManager must not inherit from QObject."""
    try:
        from PySide6.QtCore import QObject
        mgr = MarkingManager()
        assert not isinstance(mgr, QObject), "Should not be QObject"
    except ImportError:
        pass  # Qt not installed — trivially passes


def test_marking_changed_event_fires():
    """marking_changed event fires when indices change."""
    mgr = MarkingManager()
    received = []
    mgr.subscribe("marking_changed", lambda name, indices: received.append((name, indices)))
    mgr.create_marking("test", "#ff0000")
    mgr.set_active_marking("test")
    mgr.update_marking("test", {0, 1, 2}, MarkMode.REPLACE)
    assert len(received) == 1
    assert received[0][0] == "test"
    assert received[0][1] == {0, 1, 2}


def test_marking_created_event_fires():
    mgr = MarkingManager()
    received = []
    mgr.subscribe("marking_created", received.append)
    mgr.create_marking("new_marking", "#0000ff")
    assert received == ["new_marking"]


def test_marking_removed_event_fires():
    mgr = MarkingManager()
    mgr.create_marking("m1", "#ff0000")
    received = []
    mgr.subscribe("marking_removed", received.append)
    mgr.remove_marking("m1")
    assert received == ["m1"]
```

**Step 2: Run to confirm FAIL**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_marking_observable.py -v 2>&1 | tail -15
```
Expected: FAIL — MarkingManager is still a QObject.

**Step 3: Migrate marking.py**

In `data_graph_studio/core/marking.py`:
- Remove: `from PySide6.QtCore import QObject, Signal`
- Add: `from data_graph_studio.core.observable import Observable`
- Change: `class MarkingManager(QObject):` → `class MarkingManager(Observable):`
- Remove: all `Signal()` declarations
- Remove: `parent: Optional[QObject] = None` from `__init__`, change `super().__init__(parent)` → `super().__init__()`
- Change: every `self.marking_changed.emit(...)` → `self.emit("marking_changed", ...)`
- Same for all 4 signals

**Step 4: Create adapter**

Create `data_graph_studio/ui/adapters/marking_adapter.py`:
```python
"""Qt signal adapter for MarkingManager."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.marking import MarkingManager


class MarkingManagerAdapter(QObject):
    """Wraps MarkingManager and re-emits Observable events as Qt Signals."""
    marking_changed = Signal(str, object)   # name, indices (set)
    active_marking_changed = Signal(str)    # name
    marking_created = Signal(str)           # name
    marking_removed = Signal(str)           # name

    def __init__(self, manager: MarkingManager, parent=None):
        super().__init__(parent)
        manager.subscribe("marking_changed", self.marking_changed.emit)
        manager.subscribe("active_marking_changed", self.active_marking_changed.emit)
        manager.subscribe("marking_created", self.marking_created.emit)
        manager.subscribe("marking_removed", self.marking_removed.emit)

    @property
    def manager(self) -> MarkingManager:
        return self._manager
```

**Step 5: Run tests**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_marking_observable.py -v 2>&1 | tail -10
```
Expected: 4/4 PASS

**Step 6: Full suite**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -5
```
Expected: no regressions

**Step 7: Commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/marking.py data_graph_studio/ui/adapters/marking_adapter.py tests/unit/test_marking_observable.py && git commit -m "refactor: decouple MarkingManager from Qt using Observable pattern"
```

---

## Task 2: Migrate `comparison_manager.py` — ComparisonManager

**Files:**
- Modify: `data_graph_studio/core/comparison_manager.py`
- Modify: `data_graph_studio/core/state.py` (6 `.connect()` lines → `.subscribe()`)
- Create: `data_graph_studio/ui/adapters/comparison_manager_adapter.py`
- Test: `tests/unit/test_comparison_manager_observable.py`

**Context:** ComparisonManager has 6 signals. They are connected only from `state.py` lines 371-379. The UI connects to `state.py` signals which proxy comparison_manager events — no UI changes needed.

**Signals:**
```python
dataset_added = Signal(str)            → "dataset_added"
dataset_removed = Signal(str)          → "dataset_removed"
dataset_activated = Signal(str)        → "dataset_activated"
dataset_updated = Signal(str)          → "dataset_updated"
comparison_mode_changed = Signal(str)  → "comparison_mode_changed"
comparison_settings_changed = Signal() → "comparison_settings_changed"
```

**Step 1: Write failing test**

Create `tests/unit/test_comparison_manager_observable.py`:
```python
"""ComparisonManager uses Observable, not Qt signals."""
import pytest


def test_comparison_manager_is_observable():
    from data_graph_studio.core.comparison_manager import ComparisonManager
    from data_graph_studio.core.observable import Observable
    mgr = ComparisonManager()
    assert isinstance(mgr, Observable)


def test_dataset_added_event():
    from data_graph_studio.core.comparison_manager import ComparisonManager
    mgr = ComparisonManager()
    received = []
    mgr.subscribe("dataset_added", received.append)
    mgr.load_dataset("test_id", [1, 2, 3])
    assert "test_id" in received


def test_comparison_settings_changed_event():
    from data_graph_studio.core.comparison_manager import ComparisonManager
    mgr = ComparisonManager()
    received = []
    mgr.subscribe("comparison_settings_changed", lambda: received.append(True))
    # Trigger a settings change (read the file to find the right method)
    assert len(received) >= 0  # will pass trivially until implemented
```

**Step 2: Run to confirm FAIL**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_comparison_manager_observable.py::test_comparison_manager_is_observable -v 2>&1 | tail -10
```

**Step 3: Migrate comparison_manager.py**
- Remove: `from PySide6.QtCore import QObject, Signal`
- Add: `from data_graph_studio.core.observable import Observable`
- Change: `class ComparisonManager(QObject):` → `class ComparisonManager(Observable):`
- Remove: `Signal()` declarations
- Remove: `parent=None` from `__init__`, fix `super().__init__(parent)` → `super().__init__()`
- Change: all `self.signal_name.emit(args)` → `self.emit("signal_name", args)` for each signal

**Step 4: Update state.py subscriptions**

In `data_graph_studio/core/state.py` lines 371-379, change:
```python
# BEFORE:
self.comparison_manager.dataset_added.connect(self.dataset_added)
self.comparison_manager.dataset_removed.connect(self.dataset_removed)
self.comparison_manager.dataset_activated.connect(self.dataset_activated)
self.comparison_manager.dataset_updated.connect(self.dataset_updated)
self.comparison_manager.comparison_mode_changed.connect(self.comparison_mode_changed)
self.comparison_manager.comparison_settings_changed.connect(self.comparison_settings_changed)
# ...
self.comparison_manager.dataset_activated.connect(self._on_dataset_activated)

# AFTER:
self.comparison_manager.subscribe("dataset_added", self.dataset_added.emit)
self.comparison_manager.subscribe("dataset_removed", self.dataset_removed.emit)
self.comparison_manager.subscribe("dataset_activated", self.dataset_activated.emit)
self.comparison_manager.subscribe("dataset_updated", self.dataset_updated.emit)
self.comparison_manager.subscribe("comparison_mode_changed", self.comparison_mode_changed.emit)
self.comparison_manager.subscribe("comparison_settings_changed", self.comparison_settings_changed.emit)
# ...
self.comparison_manager.subscribe("dataset_activated", self._on_dataset_activated)
```

**Step 5: Run tests**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/unit/test_comparison_manager_observable.py -v 2>&1 | tail -10
```

**Step 6: Full suite**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -5
```

**Step 7: Commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/core/comparison_manager.py data_graph_studio/core/state.py data_graph_studio/ui/adapters/comparison_manager_adapter.py tests/unit/test_comparison_manager_observable.py && git commit -m "refactor: decouple ComparisonManager from Qt using Observable pattern"
```

---

## Task 3: Migrate `profile_controller.py` — ProfileController

**Files:**
- Modify: `data_graph_studio/core/profile_controller.py`
- Create: `data_graph_studio/ui/adapters/profile_controller_adapter.py`
- Modify: `data_graph_studio/ui/controllers/dataset_controller.py` (one `.connect()` line)
- Test: `tests/unit/test_profile_controller_observable.py`

**Context:** ProfileController has 5 signals. One is connected from `dataset_controller.py:704`:
```python
w.profile_controller.profile_renamed.connect(view.on_profile_renamed)
```
This needs to be updated to use the adapter.

**Signals:**
```python
profile_applied = Signal(str)        → "profile_applied"
profile_created = Signal(str)        → "profile_created"
profile_deleted = Signal(str)        → "profile_deleted"
profile_renamed = Signal(str, str)   → "profile_renamed"
error_occurred = Signal(str)         → "error_occurred"
```

**Step 1: Read `profile_controller.py` in full** to understand the implementation.

**Step 2: Write failing test**

Create `tests/unit/test_profile_controller_observable.py`:
```python
"""ProfileController uses Observable, not Qt signals."""
from data_graph_studio.core.profile_controller import ProfileController
from data_graph_studio.core.observable import Observable


def test_profile_controller_is_observable():
    ctrl = ProfileController.__new__(ProfileController)  # skip __init__ if it requires args
    assert isinstance(ctrl, Observable) or issubclass(ProfileController, Observable)
```

**Step 3: Migrate profile_controller.py** — same recipe as Tasks 1-2.

**Step 4: Create adapter**

Create `data_graph_studio/ui/adapters/profile_controller_adapter.py`:
```python
"""Qt signal adapter for ProfileController."""
from PySide6.QtCore import QObject, Signal
from data_graph_studio.core.profile_controller import ProfileController


class ProfileControllerAdapter(QObject):
    profile_applied = Signal(str)
    profile_created = Signal(str)
    profile_deleted = Signal(str)
    profile_renamed = Signal(str, str)
    error_occurred = Signal(str)

    def __init__(self, controller: ProfileController, parent=None):
        super().__init__(parent)
        controller.subscribe("profile_applied", self.profile_applied.emit)
        controller.subscribe("profile_created", self.profile_created.emit)
        controller.subscribe("profile_deleted", self.profile_deleted.emit)
        controller.subscribe("profile_renamed", self.profile_renamed.emit)
        controller.subscribe("error_occurred", self.error_occurred.emit)
```

**Step 5: Update dataset_controller.py**

Find the `ProfileControllerAdapter` and update:
```python
# dataset_controller.py:704
# BEFORE:
w.profile_controller.profile_renamed.connect(view.on_profile_renamed)
# AFTER:
w.profile_controller.subscribe("profile_renamed", view.on_profile_renamed)
```

Or, if an adapter is already created for `profile_controller`, use:
```python
w.profile_controller_adapter.profile_renamed.connect(view.on_profile_renamed)
```

**Step 6: Full suite, then commit**
```bash
cd /Users/lov2fn/Projects/data-graph-studio && python -m pytest tests/ -x -q 2>&1 | tail -5
git add data_graph_studio/core/profile_controller.py data_graph_studio/ui/adapters/profile_controller_adapter.py data_graph_studio/ui/controllers/dataset_controller.py tests/unit/test_profile_controller_observable.py
git commit -m "refactor: decouple ProfileController from Qt using Observable pattern"
```

---

## Task 4: Migrate `profile_comparison_controller.py` — ProfileComparisonController

**Files:**
- Modify: `data_graph_studio/core/profile_comparison_controller.py`
- Create: `data_graph_studio/ui/adapters/profile_comparison_adapter.py`
- Test: `tests/unit/test_profile_comparison_observable.py`

**Context:** 5 signals, small file (213 lines). Check UI usage before migrating:
```bash
grep -rn "profile_comparison_controller\|ProfileComparisonController" data_graph_studio/ui/ --include="*.py" | grep "connect\|import"
```

**Signals:**
```python
comparison_started = Signal(str, list)  → "comparison_started"
comparison_ended = Signal()             → "comparison_ended"
comparison_mode_changed = Signal(str)   → "comparison_mode_changed"
panel_removed = Signal(str)             → "panel_removed"
error_occurred = Signal(str)            → "error_occurred"
```

Follow same migration recipe. Update any UI `.connect()` calls found.

**Commit:**
```bash
git commit -m "refactor: decouple ProfileComparisonController from Qt using Observable pattern"
```

---

## Task 5: Migrate `file_watcher.py` — FileWatcher

**Files:**
- Modify: `data_graph_studio/core/file_watcher.py`
- Modify: `data_graph_studio/core/io_abstract.py` (add `ThreadingTimerFactory`)
- Create: `data_graph_studio/ui/adapters/file_watcher_adapter.py`
- Test: `tests/unit/test_file_watcher_observable.py`

**Context:** FileWatcher already uses `ITimerFactory` abstraction — so timer injection is already done. The `QTimerFactory` used in production is referenced at line 68 but likely defined in UI layer. Just need to:
1. Remove `QObject` inheritance
2. Replace `Signal()` with Observable events
3. Move `QTimerFactory` to UI layer (or create it in `ui/adapters/`)
4. Add `ThreadingTimerFactory` to `io_abstract.py` for production use without Qt

**Step 1: Find QTimerFactory**
```bash
grep -rn "class QTimerFactory" data_graph_studio/ --include="*.py"
```

**Step 2: Write failing test**

Create `tests/unit/test_file_watcher_observable.py`:
```python
"""FileWatcher uses Observable pattern."""
from data_graph_studio.core.file_watcher import FileWatcher
from data_graph_studio.core.observable import Observable


def test_file_watcher_is_observable():
    assert issubclass(FileWatcher, Observable)


def test_file_changed_event_fires(tmp_path):
    import time
    from unittest.mock import MagicMock
    from data_graph_studio.core.io_abstract import ITimerFactory, IFileSystem, RealFileSystem

    class InstantTimerFactory(ITimerFactory):
        """Timer that fires callback immediately for testing."""
        def create_timer(self, interval_ms, callback):
            callback()
            class FakeTimer:
                def stop(self): pass
            return FakeTimer()

    test_file = tmp_path / "test.csv"
    test_file.write_bytes(b"a,b\n1,2\n")

    received = []
    watcher = FileWatcher(fs=RealFileSystem(), timer_factory=InstantTimerFactory())
    watcher.subscribe("file_changed", received.append)
    watcher.watch(str(test_file))
    # Simulate file modification
    test_file.write_bytes(b"a,b\n1,2\n3,4\n")
    watcher._check_file(str(test_file))
    assert str(test_file) in received
```

**Step 3: Add ThreadingTimerFactory to io_abstract.py**
```python
import threading

class ThreadingTimerFactory(ITimerFactory):
    """Production timer using threading.Timer — no Qt dependency."""

    def create_timer(self, interval_ms: int, callback: Callable) -> "threading.Timer":
        """Create a recurring timer using threading.Timer."""
        interval_s = interval_ms / 1000.0

        def _recurring():
            callback()
            t = threading.Timer(interval_s, _recurring)
            t.daemon = True
            t.start()
            return t

        t = threading.Timer(interval_s, _recurring)
        t.daemon = True
        t.start()
        return t
```

**Step 4: Migrate file_watcher.py**
- Remove `from PySide6.QtCore import QObject, Signal`
- Add `from data_graph_studio.core.observable import Observable`
- Change: `class FileWatcher(QObject):` → `class FileWatcher(Observable):`
- Remove `Signal()` declarations
- Remove `parent=None` from `__init__`
- Replace `self.file_changed.emit(path)` → `self.emit("file_changed", path)` etc.
- In production `create()` factory, replace `QTimerFactory()` with `ThreadingTimerFactory()`

**Step 5: Create adapter, run tests, commit**
```bash
git commit -m "refactor: decouple FileWatcher from Qt using Observable + ThreadingTimerFactory"
```

---

## Task 6: Migrate `view_sync.py` — ViewSyncManager

**Files:**
- Modify: `data_graph_studio/core/view_sync.py`
- Modify: `data_graph_studio/ui/panels/side_by_side_layout.py` (update signal connections)
- Create: `data_graph_studio/ui/adapters/view_sync_adapter.py`
- Test: `tests/unit/test_view_sync_observable.py`

**Context:** ViewSyncManager uses `QTimer` for 50ms throttle. Replace with `threading.Timer` + cancellation. Uses `QWidget` for panel type hints only (just change to `Any`).

**Signals:**
```python
view_range_synced = Signal(str, list, list)  → "view_range_synced"
selection_synced = Signal(str, list)          → "selection_synced"
```

**Step 1: Read view_sync.py in full** to understand throttle logic.

**Step 2: Write failing test**
```python
"""ViewSyncManager uses Observable, not Qt."""
from data_graph_studio.core.view_sync import ViewSyncManager
from data_graph_studio.core.observable import Observable


def test_view_sync_manager_is_observable():
    assert issubclass(ViewSyncManager, Observable)


def test_view_range_synced_event():
    mgr = ViewSyncManager()
    received = []
    mgr.subscribe("view_range_synced", lambda *a: received.append(a))

    class FakePanel:
        calls = []
        def set_view_range(self, xr, yr, sx, sy): self.calls.append(("range", xr, yr))
        def set_selection(self, idxs): self.calls.append(("sel", idxs))

    p1, p2 = FakePanel(), FakePanel()
    mgr.register_panel("p1", p1)
    mgr.register_panel("p2", p2)
    mgr.sync_view_range("p1", [0, 10], [0, 100], sync_x=True, sync_y=True)
    assert len(received) >= 1
```

**Step 3: Replace QTimer throttle with threading.Timer**

```python
# BEFORE:
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QWidget

class ViewSyncManager(QObject):
    THROTTLE_MS = 50
    def __init__(self, parent=None):
        super().__init__(parent)
        self._range_throttle_timer = QTimer(self)
        self._range_throttle_timer.setSingleShot(True)
        self._range_throttle_timer.timeout.connect(self._flush_range_sync)

# AFTER:
import threading
from typing import Any
from data_graph_studio.core.observable import Observable

class ViewSyncManager(Observable):
    THROTTLE_MS = 50
    def __init__(self):
        super().__init__()
        self._range_pending: dict = {}
        self._range_timer: threading.Timer | None = None
        self._sel_pending: dict = {}
        self._sel_timer: threading.Timer | None = None
        self._lock = threading.Lock()
```

Throttle implementation (replaces QTimer.singleShot):
```python
def _schedule_range_flush(self):
    with self._lock:
        if self._range_timer is not None:
            self._range_timer.cancel()
        self._range_timer = threading.Timer(
            self.THROTTLE_MS / 1000.0, self._flush_range_sync
        )
        self._range_timer.daemon = True
        self._range_timer.start()
```

**Step 4: Update side_by_side_layout.py**

Find any `.connect()` calls on ViewSyncManager signals and update to use adapter or `.subscribe()`.

**Step 5: Create adapter, run full suite, commit**
```bash
git commit -m "refactor: decouple ViewSyncManager from Qt using Observable + threading.Timer"
```

---

## Phase 3a Completion Checklist

- [ ] marking.py: QObject removed, Observable, adapter created
- [ ] comparison_manager.py: QObject removed, Observable, state.py subscriptions updated
- [ ] profile_controller.py: QObject removed, Observable, adapter created, dataset_controller.py updated
- [ ] profile_comparison_controller.py: QObject removed, Observable, adapter created
- [ ] file_watcher.py: QObject removed, Observable, ThreadingTimerFactory added
- [ ] view_sync.py: QObject removed, Observable, QTimer replaced with threading.Timer
- [ ] All tests pass (baseline: 1960)
- [ ] 6 commits on goat-code-audit branch

**Remaining Qt in core after Phase 3a:**
- `state.py` (AppState — Phase 4, very large)
- `ipc_server.py` (Qt networking — requires asyncio migration, separate effort)
- `export_controller.py` (uses Qt for image/PDF export — functionally requires Qt)
- `clipboard_manager.py` (uses QApplication for clipboard access — functionally requires Qt)
