"""Regression tests for MainGraph mouse event sequences (selection/drawing)."""

from __future__ import annotations

import numpy as np
import pytest
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent

from data_graph_studio.core.state import AppState, ToolMode
from data_graph_studio.ui.panels.main_graph import MainGraph


class _FakeMouseEvent:
    def __init__(self, x: float, y: float, button=Qt.LeftButton):
        self._pos = QPointF(x, y)
        self._button = button
        self.accepted = False

    def position(self):
        return self._pos

    def button(self):
        return self._button

    def accept(self):
        self.accepted = True


def _qt_release_event(x: float, y: float) -> QMouseEvent:
    p = QPointF(x, y)
    return QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        p,
        p,
        p,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )


@pytest.fixture()
def state(qtbot):
    return AppState()


@pytest.fixture()
def graph(state, qtbot):
    w = MainGraph(state)
    qtbot.addWidget(w)
    # Make scene→view mapping deterministic for synthetic events.
    w.plotItem.vb.mapSceneToView = lambda p: p
    return w


class TestMainGraphMouseEventSequence:
    @pytest.mark.skip(reason="rect selection changed in release")
    def test_rect_select_press_move_release_selects_expected_points(self, graph, state):
        state.set_tool_mode(ToolMode.RECT_SELECT)
        graph._data_x = np.array([0.0, 5.0, 10.0])
        graph._data_y = np.array([0.0, 5.0, 10.0])

        graph.mousePressEvent(_FakeMouseEvent(0.0, 0.0))
        graph.mouseMoveEvent(_FakeMouseEvent(6.0, 6.0))
        graph.mouseReleaseEvent(_FakeMouseEvent(6.0, 6.0))

        assert state.selection.selected_rows == {0, 1}
        assert graph._is_selecting is False
        assert graph._selection_roi is None

    def test_mode_switch_during_rect_drag_cleans_stale_selection_state(
        self, graph, state
    ):
        """중간에 툴 모드를 바꿔도 stale selection state가 남지 않아야 한다."""
        state.set_tool_mode(ToolMode.RECT_SELECT)
        graph._data_x = np.array([0.0, 5.0, 10.0])
        graph._data_y = np.array([0.0, 5.0, 10.0])

        graph.mousePressEvent(_FakeMouseEvent(0.0, 0.0))
        graph.mouseMoveEvent(_FakeMouseEvent(6.0, 6.0))

        # Drag 도중 모드 전환
        state.set_tool_mode(ToolMode.PAN)
        graph.mouseReleaseEvent(_qt_release_event(6.0, 6.0))

        assert graph._is_selecting is False
        assert graph._selection_roi is None

    def test_line_draw_press_release_calls_finish_once(self, graph, state, monkeypatch):
        state.set_tool_mode(ToolMode.LINE_DRAW)

        calls = []

        def _fake_finish(x, y):
            calls.append((x, y))
            graph._cleanup_drawing()

        monkeypatch.setattr(graph, "_finish_drawing", _fake_finish)

        graph.mousePressEvent(_FakeMouseEvent(1.0, 2.0))
        graph.mouseReleaseEvent(_FakeMouseEvent(3.0, 4.0))

        assert calls == [(3.0, 4.0)]
        assert graph._is_drawing is False
