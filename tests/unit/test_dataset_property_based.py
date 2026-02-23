"""
Property-based tests for DatasetManager invariants.

Uses pytest.mark.parametrize to verify structural invariants:
- Adding N datasets → len(manager) == N  (for N in 1..MAX_DATASETS)
- Remove after add → count decreases by exactly 1
- DatasetInfo.column_count matches the underlying DataFrame column count
- DatasetInfo.row_count matches the underlying DataFrame row count
- DatasetInfo.columns matches DataFrame.columns

All tests are Qt-free.
"""

from unittest.mock import MagicMock

import polars as pl
import pytest

from data_graph_studio.core.dataset_manager import DatasetManager
from data_graph_studio.core.types import DatasetInfo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager() -> DatasetManager:
    loader = MagicMock()
    loader._df = None
    loader._lazy_df = None
    loader._source = None
    loader._profile = None
    return DatasetManager(loader)


def _add_df(manager: DatasetManager, rows: int = 3, cols: int = 2, name: str = "ds") -> str:
    data = {f"col_{c}": list(range(rows)) for c in range(cols)}
    df = pl.DataFrame(data)
    did = manager.load_dataset_from_dataframe(df, name=name)
    assert did is not None
    return did


# ---------------------------------------------------------------------------
# Property 1: Adding N datasets → dataset_count == N
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 5, 10])
def test_dataset_count_equals_added(n):
    """After adding N datasets, dataset_count is exactly N."""
    manager = _make_manager()
    for i in range(n):
        _add_df(manager, name=f"ds_{i}")
    assert manager.dataset_count == n


@pytest.mark.parametrize("n", [1, 2, 5, 10])
def test_dataset_count_equals_len_of_datasets_dict(n):
    """dataset_count matches len(manager.datasets) at all times."""
    manager = _make_manager()
    for i in range(n):
        _add_df(manager, name=f"ds_{i}")
    assert manager.dataset_count == len(manager.datasets)


# ---------------------------------------------------------------------------
# Property 2: Remove after add → count decreases by exactly 1
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 2, 5, 10])
def test_remove_decreases_count_by_one(n):
    """Removing one dataset from a manager with N datasets yields N-1."""
    manager = _make_manager()
    ids = [_add_df(manager, name=f"ds_{i}") for i in range(n)]
    target = ids[n // 2]  # remove something from the middle

    before = manager.dataset_count
    result = manager.remove_dataset(target)

    assert result is True
    assert manager.dataset_count == before - 1


@pytest.mark.parametrize("n", [2, 3, 5])
def test_remove_all_yields_zero(n):
    """Removing every dataset one by one ends at count 0."""
    manager = _make_manager()
    ids = [_add_df(manager, name=f"ds_{i}") for i in range(n)]
    for did in ids:
        manager.remove_dataset(did)
    assert manager.dataset_count == 0


# ---------------------------------------------------------------------------
# Property 3: DatasetInfo.column_count matches DataFrame column count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("num_cols", [1, 2, 5, 10, 20])
def test_dataset_column_count_matches_dataframe(num_cols):
    """DatasetInfo.column_count == len(df.columns) for any DataFrame."""
    manager = _make_manager()
    did = _add_df(manager, rows=4, cols=num_cols)
    info = manager.get_dataset(did)
    assert info is not None
    assert info.column_count == num_cols
    assert info.column_count == len(info.df.columns)


@pytest.mark.parametrize("num_cols", [1, 3, 7])
def test_dataset_columns_list_matches_dataframe(num_cols):
    """DatasetInfo.columns == df.columns for any DataFrame."""
    manager = _make_manager()
    did = _add_df(manager, rows=4, cols=num_cols)
    info = manager.get_dataset(did)
    assert info is not None
    assert info.columns == info.df.columns


# ---------------------------------------------------------------------------
# Property 4: DatasetInfo.row_count matches DataFrame row count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("num_rows", [0, 1, 5, 100, 1000])
def test_dataset_row_count_matches_dataframe(num_rows):
    """DatasetInfo.row_count == len(df) for any DataFrame."""
    manager = _make_manager()
    df = pl.DataFrame({"x": list(range(num_rows))})
    did = manager.load_dataset_from_dataframe(df, name="test")
    info = manager.get_dataset(did)
    assert info is not None
    assert info.row_count == num_rows
    assert info.row_count == len(info.df)


@pytest.mark.parametrize("num_rows", [1, 10, 50])
def test_row_count_unchanged_after_retrieve(num_rows):
    """Retrieving a dataset multiple times always returns consistent row_count."""
    manager = _make_manager()
    df = pl.DataFrame({"val": list(range(num_rows))})
    did = manager.load_dataset_from_dataframe(df, name="stable")

    for _ in range(3):
        info = manager.get_dataset(did)
        assert info.row_count == num_rows


# ---------------------------------------------------------------------------
# Property 5: get_dataset_df returns the same DataFrame as DatasetInfo.df
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("num_rows,num_cols", [(3, 2), (10, 5), (1, 1)])
def test_get_dataset_df_matches_info_df(num_rows, num_cols):
    """get_dataset_df returns the identical DataFrame held in DatasetInfo."""
    manager = _make_manager()
    did = _add_df(manager, rows=num_rows, cols=num_cols)
    info = manager.get_dataset(did)
    df_direct = manager.get_dataset_df(did)
    assert df_direct is not None
    # Use identity check — both should be the exact same object
    assert df_direct is info.df


# ---------------------------------------------------------------------------
# Property 6: Dataset IDs are unique
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [2, 5, 10])
def test_all_dataset_ids_are_unique(n):
    """Each loaded dataset gets a distinct ID."""
    manager = _make_manager()
    ids = [_add_df(manager, name=f"ds_{i}") for i in range(n)]
    assert len(set(ids)) == n


# ---------------------------------------------------------------------------
# Property 7: First dataset added becomes active
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("extra", [0, 1, 4])
def test_first_dataset_becomes_active(extra):
    """The first dataset loaded is set as active_dataset_id."""
    manager = _make_manager()
    first_id = _add_df(manager, name="first")
    for i in range(extra):
        _add_df(manager, name=f"extra_{i}")
    assert manager.active_dataset_id == first_id


# ---------------------------------------------------------------------------
# Property 8: list_datasets length matches dataset_count
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [0, 1, 3, 10])
def test_list_datasets_length_matches_count(n):
    """list_datasets() returns exactly dataset_count items."""
    manager = _make_manager()
    for i in range(n):
        _add_df(manager, name=f"ds_{i}")
    assert len(manager.list_datasets()) == manager.dataset_count


# ---------------------------------------------------------------------------
# Property 9: clear_all_datasets resets to zero
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n", [1, 3, 10])
def test_clear_all_datasets_resets_count(n):
    """clear_all_datasets() leaves dataset_count == 0."""
    manager = _make_manager()
    for i in range(n):
        _add_df(manager, name=f"ds_{i}")
    manager.clear_all_datasets()
    assert manager.dataset_count == 0
    assert manager.active_dataset_id is None
