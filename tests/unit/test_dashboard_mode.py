"""
Tests for Dashboard Mode (Feature 1) — PRD v2

TDD: tests written before implementation.

UT-1.1: DashboardLayout 생성/직렬화/역직렬화
UT-1.2: 셀 스팬 유효성 검증 (겹침 방지)
UT-1.3: 셀 추가/제거
UT-1.4: 셀 리사이즈 (스팬 변경)
UT-1.5: 최소 셀 크기 검증 (240×180)
UT-1.6: JSON 스키마 검증 실패 → 기본 레이아웃 폴백
UT-1.7: 축 동기화 (sync_x=True)
UT-1.8: 빈 데이터셋에서 대시보드 활성화 차단
"""

from __future__ import annotations

import copy
import json
import sys
import os
import pytest
from unittest.mock import MagicMock, patch, PropertyMock

# Ensure project root is on sys.path
PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..")
)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from data_graph_studio.core.dashboard_layout import (
    DashboardCell,
    DashboardLayout,
    validate_layout_json,
    default_layout,
    LAYOUT_PRESETS,
    MIN_CELL_WIDTH,
    MIN_CELL_HEIGHT,
)
from data_graph_studio.core.dashboard_controller import DashboardController
from data_graph_studio.core.undo_manager import UndoStack, UndoActionType
from data_graph_studio.graph.sampling import DataSampler

import numpy as np


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def undo_stack():
    return UndoStack(max_depth=50)


@pytest.fixture
def mock_state():
    """Minimal AppState mock."""
    state = MagicMock()
    state.dataset_count = 0
    state._dataset_states = {}
    state.dataset_states = {}
    state.is_profile_comparison_active = False
    state.clear_profile_comparison = MagicMock()
    state.comparison_settings = MagicMock()
    state.comparison_settings.comparison_target = "dataset"
    return state


@pytest.fixture
def controller(mock_state, undo_stack):
    return DashboardController(state=mock_state, undo_stack=undo_stack)


# ===========================================================================
# UT-1.1: DashboardLayout 생성/직렬화/역직렬화
# ===========================================================================


class TestDashboardLayoutSerialization:
    """UT-1.1"""

    def test_create_layout_defaults(self):
        layout = DashboardLayout(name="Test", rows=2, cols=2, cells=[])
        assert layout.name == "Test"
        assert layout.rows == 2
        assert layout.cols == 2
        assert layout.cells == []
        assert layout.sync_x is False
        assert layout.sync_y is False

    def test_create_cell(self):
        cell = DashboardCell(row=0, col=1, row_span=1, col_span=2, profile_id="p1")
        assert cell.row == 0
        assert cell.col == 1
        assert cell.row_span == 1
        assert cell.col_span == 2
        assert cell.profile_id == "p1"

    def test_to_dict_round_trip(self):
        cells = [
            DashboardCell(row=0, col=0, profile_id="a"),
            DashboardCell(row=0, col=1, row_span=2, col_span=1, profile_id="b"),
        ]
        layout = DashboardLayout(
            name="My Dashboard", rows=3, cols=3, cells=cells, sync_x=True, sync_y=False,
        )
        d = layout.to_dict()
        restored = DashboardLayout.from_dict(d)

        assert restored.name == layout.name
        assert restored.rows == layout.rows
        assert restored.cols == layout.cols
        assert restored.sync_x is True
        assert restored.sync_y is False
        assert len(restored.cells) == 2
        assert restored.cells[0].profile_id == "a"
        assert restored.cells[1].row_span == 2

    def test_json_serialization(self):
        layout = DashboardLayout(name="J", rows=2, cols=2, cells=[
            DashboardCell(row=0, col=0, profile_id="x"),
        ])
        json_str = json.dumps(layout.to_dict())
        data = json.loads(json_str)
        restored = DashboardLayout.from_dict(data)
        assert restored.name == "J"
        assert len(restored.cells) == 1

    def test_json_size_under_10kb(self):
        """NFR-1.3: JSON < 10KB even for 3×3 with all cells filled."""
        cells = [
            DashboardCell(row=r, col=c, profile_id=f"profile_{r}_{c}")
            for r in range(3)
            for c in range(3)
        ]
        layout = DashboardLayout(name="Full 3×3", rows=3, cols=3, cells=cells, sync_x=True)
        json_str = json.dumps(layout.to_dict())
        assert len(json_str.encode("utf-8")) < 10240


# ===========================================================================
# UT-1.2: 셀 스팬 유효성 검증 (겹침 방지)
# ===========================================================================


class TestCellSpanValidation:
    """UT-1.2"""

    def test_no_overlap_valid(self):
        cells = [
            DashboardCell(row=0, col=0),
            DashboardCell(row=0, col=1),
            DashboardCell(row=1, col=0),
            DashboardCell(row=1, col=1),
        ]
        layout = DashboardLayout(name="t", rows=2, cols=2, cells=cells)
        assert layout.validate() is True

    def test_overlap_detected(self):
        cells = [
            DashboardCell(row=0, col=0, col_span=2),  # occupies (0,0) and (0,1)
            DashboardCell(row=0, col=1),               # overlaps with first cell at (0,1)
        ]
        layout = DashboardLayout(name="t", rows=2, cols=2, cells=cells)
        assert layout.validate() is False

    def test_span_exceeds_grid(self):
        cells = [
            DashboardCell(row=0, col=0, row_span=3),  # 3 rows in a 2-row grid
        ]
        layout = DashboardLayout(name="t", rows=2, cols=2, cells=cells)
        assert layout.validate() is False

    def test_row_span_overlap(self):
        cells = [
            DashboardCell(row=0, col=0, row_span=2),  # occupies (0,0) and (1,0)
            DashboardCell(row=1, col=0),               # overlaps at (1,0)
        ]
        layout = DashboardLayout(name="t", rows=2, cols=2, cells=cells)
        assert layout.validate() is False


# ===========================================================================
# UT-1.3: 셀 추가/제거
# ===========================================================================


class TestCellAddRemove:
    """UT-1.3"""

    def test_add_cell(self, controller, undo_stack):
        controller.create_layout("Test", 2, 2)
        controller.add_cell(0, 0, profile_id="p1")
        layout = controller.current_layout
        assert len(layout.cells) == 1
        assert layout.cells[0].profile_id == "p1"

    def test_remove_cell(self, controller, undo_stack):
        controller.create_layout("Test", 2, 2)
        controller.add_cell(0, 0, profile_id="p1")
        controller.add_cell(0, 1, profile_id="p2")
        assert len(controller.current_layout.cells) == 2

        controller.remove_cell(0, 0)
        assert len(controller.current_layout.cells) == 1
        assert controller.current_layout.cells[0].profile_id == "p2"

    def test_remove_nonexistent_cell(self, controller):
        controller.create_layout("Test", 2, 2)
        # Should not raise
        controller.remove_cell(0, 0)
        assert len(controller.current_layout.cells) == 0

    def test_add_cell_undo(self, controller, undo_stack):
        controller.create_layout("Test", 2, 2)
        controller.add_cell(0, 0, profile_id="p1")
        assert undo_stack.can_undo()


# ===========================================================================
# UT-1.4: 셀 리사이즈 (스팬 변경)
# ===========================================================================


class TestCellResize:
    """UT-1.4"""

    def test_resize_cell_span(self, controller):
        controller.create_layout("Test", 3, 3)
        controller.add_cell(0, 0, profile_id="p1")
        controller.resize_cell(0, 0, row_span=2, col_span=2)

        cell = controller.get_cell(0, 0)
        assert cell is not None
        assert cell.row_span == 2
        assert cell.col_span == 2

    def test_resize_cell_overlap_rejected(self, controller):
        controller.create_layout("Test", 3, 3)
        controller.add_cell(0, 0, profile_id="p1")
        controller.add_cell(0, 1, profile_id="p2")

        # Expanding cell at (0,0) to col_span=2 would overlap (0,1)
        success = controller.resize_cell(0, 0, row_span=1, col_span=2)
        assert success is False
        cell = controller.get_cell(0, 0)
        assert cell.col_span == 1  # unchanged


# ===========================================================================
# UT-1.5: 최소 셀 크기 검증 (240×180)
# ===========================================================================


class TestMinimumCellSize:
    """UT-1.5"""

    def test_min_cell_constants(self):
        assert MIN_CELL_WIDTH == 240
        assert MIN_CELL_HEIGHT == 180

    def test_minimum_window_size_for_layout(self):
        """3×3 layout requires at least 3×240=720 width and 3×180=540 height."""
        layout = DashboardLayout(name="t", rows=3, cols=3, cells=[])
        min_w, min_h = layout.minimum_window_size()
        assert min_w >= 3 * MIN_CELL_WIDTH
        assert min_h >= 3 * MIN_CELL_HEIGHT

    def test_1x1_minimum_size(self):
        layout = DashboardLayout(name="t", rows=1, cols=1, cells=[])
        min_w, min_h = layout.minimum_window_size()
        assert min_w >= MIN_CELL_WIDTH
        assert min_h >= MIN_CELL_HEIGHT


# ===========================================================================
# UT-1.6: JSON 스키마 검증 실패 → 기본 레이아웃 폴백
# ===========================================================================


class TestJsonSchemaFallback:
    """UT-1.6"""

    def test_valid_json(self):
        layout = DashboardLayout(name="ok", rows=2, cols=2, cells=[])
        result = validate_layout_json(layout.to_dict())
        assert result is not None
        assert result.name == "ok"

    def test_invalid_json_missing_rows(self):
        data = {"name": "bad", "cols": 2, "cells": []}
        result = validate_layout_json(data)
        # Should fallback to default
        assert result is not None
        assert result.rows == 2  # default 2×2
        assert result.cols == 2

    def test_invalid_json_bad_cell(self):
        data = {
            "name": "bad",
            "rows": 2,
            "cols": 2,
            "cells": [{"row": "not_a_number"}],
        }
        result = validate_layout_json(data)
        # Fallback
        assert result is not None
        assert result.rows == 2
        assert result.cols == 2

    def test_invalid_json_overlapping_cells(self):
        data = {
            "name": "overlap",
            "rows": 2,
            "cols": 2,
            "cells": [
                {"row": 0, "col": 0, "col_span": 2, "profile_id": "a"},
                {"row": 0, "col": 1, "profile_id": "b"},
            ],
        }
        result = validate_layout_json(data)
        # Fallback to default
        assert result is not None
        assert result.name != "overlap"  # fell back

    def test_default_layout(self):
        dl = default_layout()
        assert dl.rows == 2
        assert dl.cols == 2
        assert dl.name == "Default"


# ===========================================================================
# UT-1.7: 축 동기화 (sync_x=True)
# ===========================================================================


class TestAxisSync:
    """UT-1.7"""

    def test_sync_x_flag(self, controller):
        controller.create_layout("Synced", 2, 2)
        controller.set_sync_x(True)
        assert controller.current_layout.sync_x is True

    def test_sync_y_flag(self, controller):
        controller.create_layout("Synced", 2, 2)
        controller.set_sync_y(True)
        assert controller.current_layout.sync_y is True

    def test_sync_flags_serialized(self):
        layout = DashboardLayout(
            name="s", rows=2, cols=2, cells=[], sync_x=True, sync_y=True,
        )
        d = layout.to_dict()
        restored = DashboardLayout.from_dict(d)
        assert restored.sync_x is True
        assert restored.sync_y is True

    def test_sync_x_change_undo(self, controller, undo_stack):
        controller.create_layout("T", 2, 2)
        controller.set_sync_x(True)
        assert undo_stack.can_undo()


# ===========================================================================
# UT-1.8: 빈 데이터셋에서 대시보드 활성화 차단
# ===========================================================================


class TestNoDatasetsBlock:
    """UT-1.8"""

    def test_activate_blocked_without_data(self, controller, mock_state):
        mock_state.dataset_count = 0
        mock_state.dataset_states = {}
        result = controller.activate()
        assert result is False

    def test_activate_allowed_with_data(self, controller, mock_state):
        mock_state.dataset_count = 1
        mock_state.dataset_states = {"ds1": MagicMock()}
        controller.create_layout("T", 2, 2)
        result = controller.activate()
        assert result is True
        assert controller.is_active is True

    def test_deactivate(self, controller, mock_state):
        mock_state.dataset_count = 1
        mock_state.dataset_states = {"ds1": MagicMock()}
        controller.create_layout("T", 2, 2)
        controller.activate()
        controller.deactivate()
        assert controller.is_active is False


# ===========================================================================
# Additional: DashboardController features
# ===========================================================================


class TestDashboardControllerPresets:
    """Layout presets: 1×1, 1×2, 2×1, 2×2, 1×3, 3×1, 2×3."""

    def test_presets_exist(self):
        expected = ["1×1", "1×2", "2×1", "2×2", "1×3", "3×1", "2×3"]
        for name in expected:
            assert name in LAYOUT_PRESETS

    def test_apply_preset(self, controller, mock_state):
        mock_state.dataset_count = 1
        mock_state.dataset_states = {"ds1": MagicMock()}
        controller.apply_preset("2×3")
        layout = controller.current_layout
        assert layout.rows == 2
        assert layout.cols == 3


class TestDashboardControllerCellAssign:
    """Cell profile assignment/unassignment."""

    def test_assign_profile(self, controller, undo_stack):
        controller.create_layout("T", 2, 2)
        controller.add_cell(0, 0)
        controller.assign_profile(0, 0, "prof_1")
        cell = controller.get_cell(0, 0)
        assert cell.profile_id == "prof_1"
        assert undo_stack.can_undo()

    def test_unassign_profile(self, controller):
        controller.create_layout("T", 2, 2)
        controller.add_cell(0, 0, profile_id="prof_1")
        controller.unassign_profile(0, 0)
        cell = controller.get_cell(0, 0)
        assert cell.profile_id == ""


class TestDashboardComparisonExclusive:
    """Dashboard + profile comparison are mutually exclusive (PRD §8.1)."""

    def test_activate_dashboard_clears_comparison(self, controller, mock_state):
        mock_state.dataset_count = 1
        mock_state.dataset_states = {"ds1": MagicMock()}
        mock_state.is_profile_comparison_active = True
        controller.create_layout("T", 2, 2)
        controller.activate()
        mock_state.clear_profile_comparison.assert_called_once()


class TestProfileDeletedClearsCell:
    """ERR-1.2: profile deleted → cell becomes empty."""

    def test_on_profile_deleted(self, controller):
        controller.create_layout("T", 2, 2)
        controller.add_cell(0, 0, profile_id="del_me")
        controller.add_cell(0, 1, profile_id="keep")
        controller.on_profile_deleted("del_me")
        cell = controller.get_cell(0, 0)
        assert cell.profile_id == ""
        cell2 = controller.get_cell(0, 1)
        assert cell2.profile_id == "keep"


# ===========================================================================
# LTTB downsampling tests (NFR-1.4)
# ===========================================================================


class TestLTTBDownsampling:
    """Verify existing LTTB in sampling.py works correctly for dashboard use."""

    def test_lttb_basic(self):
        x = np.arange(1000, dtype=np.float64)
        y = np.sin(x / 100.0)
        sx, sy = DataSampler.lttb(x, y, threshold=100)
        assert len(sx) == 100
        # First and last points preserved
        assert sx[0] == x[0]
        assert sx[-1] == x[-1]

    def test_lttb_no_downsample_small_data(self):
        x = np.arange(10, dtype=np.float64)
        y = x * 2
        sx, sy = DataSampler.lttb(x, y, threshold=100)
        assert len(sx) == 10  # no downsampling needed

    def test_lttb_threshold_check(self):
        """NFR-1.4: downsample when points > cell_width * 4."""
        cell_width = 400
        max_points = cell_width * 4  # 1600
        x = np.arange(5000, dtype=np.float64)
        y = np.random.randn(5000)
        sx, sy = DataSampler.lttb(x, y, threshold=max_points)
        assert len(sx) == max_points


# ===========================================================================
# DashboardLayout save/load via controller
# ===========================================================================


class TestDashboardSaveLoad:
    """FR-1.4: save/load dashboard layout."""

    def test_save_and_load(self, controller):
        controller.create_layout("Saved", 2, 3)
        controller.add_cell(0, 0, profile_id="p1")
        controller.set_sync_x(True)

        saved = controller.save_layout()
        assert isinstance(saved, dict)
        assert saved["name"] == "Saved"

        controller.create_layout("Empty", 1, 1)
        controller.load_layout(saved)
        assert controller.current_layout.name == "Saved"
        assert controller.current_layout.rows == 2
        assert controller.current_layout.cols == 3
        assert controller.current_layout.sync_x is True
        assert len(controller.current_layout.cells) == 1
