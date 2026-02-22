"""
DatasetMixin — multi-dataset management delegation methods.

Extracted from DataEngine to reduce god-object complexity.
All methods delegate to self._datasets_mgr and self._loader,
which are initialised by DataEngine.__init__.
"""

from typing import Optional, List


class DatasetMixin(object):
    """Mixin for multi-dataset management methods.

    Requires the host class to provide:
        self._datasets_mgr  — DatasetManager instance
        self._loader        — FileLoader instance
        self._clear_cache() — cache invalidation method
    """

    # -- DatasetManager: class-level constants (via properties) ---------------

    @property
    def MAX_DATASETS(self):
        """Maximum number of datasets that can be loaded simultaneously."""
        return self._datasets_mgr.MAX_DATASETS

    @property
    def MAX_TOTAL_MEMORY(self):
        """Maximum combined memory (in bytes) allowed across all loaded datasets."""
        return self._datasets_mgr.MAX_TOTAL_MEMORY

    @property
    def DEFAULT_COLORS(self):
        """Ordered list of default hex color strings assigned to new datasets."""
        return self._datasets_mgr.DEFAULT_COLORS

    # -- Properties -----------------------------------------------------------

    @property
    def datasets(self):
        """Ordered mapping of dataset ID to DatasetInfo for all loaded datasets."""
        return self._datasets_mgr.datasets

    @property
    def _datasets(self):
        return self._datasets_mgr.datasets

    @property
    def dataset_count(self):
        """Number of datasets currently held in the dataset manager."""
        return self._datasets_mgr.dataset_count

    @property
    def active_dataset_id(self):
        """ID of the currently active dataset, or None if no dataset is active."""
        return self._datasets_mgr.active_dataset_id

    @property
    def _active_dataset_id(self):
        return self._datasets_mgr._active_dataset_id

    @_active_dataset_id.setter
    def _active_dataset_id(self, value):
        self._datasets_mgr._active_dataset_id = value

    @property
    def active_dataset(self):
        """DatasetInfo for the currently active dataset, or None if no dataset is active."""
        return self._datasets_mgr.active_dataset

    @property
    def _color_index(self):
        return self._datasets_mgr._color_index

    @_color_index.setter
    def _color_index(self, value):
        self._datasets_mgr._color_index = value

    # -- Lookup ---------------------------------------------------------------

    def get_dataset(self, did):
        """Return the DatasetInfo for the given dataset ID, or None if it does not exist.

        Args:
            did: Dataset ID string to look up.

        Returns:
            The DatasetInfo for the given ID, or None if it does not exist.
        """
        return self._datasets_mgr.get_dataset(did)

    def get_dataset_df(self, did):
        """Return the Polars DataFrame for the given dataset ID, or None if unavailable.

        Args:
            did: Dataset ID string to look up.

        Returns:
            The Polars DataFrame for the given dataset ID, or None if unavailable.
        """
        return self._datasets_mgr.get_dataset_df(did)

    def list_datasets(self):
        """Return a list of summary dicts (id, name, row_count, column_count) for all loaded datasets."""
        return self._datasets_mgr.list_datasets()

    # -- Memory ---------------------------------------------------------------

    def get_total_memory_usage(self):
        """Return the combined estimated memory usage in bytes for all loaded datasets."""
        return self._datasets_mgr.get_total_memory_usage()

    def can_load_dataset(self, sz):
        """Check whether a new dataset of the given byte size can be loaded without exceeding memory limits.

        Args:
            sz: Estimated size in bytes of the dataset to be loaded.

        Returns:
            True if loading is within limits, False otherwise.
        """
        return self._datasets_mgr.can_load_dataset(sz)

    # -- Mutation -------------------------------------------------------------

    def set_dataset_color(self, did, c):
        """Assign a display color to the specified dataset.

        Args:
            did: Dataset ID string.
            c: Color value (hex string or name) to assign.
        """
        self._datasets_mgr.set_dataset_color(did, c)

    def rename_dataset(self, did, n):
        """Rename the specified dataset.

        Args:
            did: Dataset ID string.
            n: New name string for the dataset.
        """
        self._datasets_mgr.rename_dataset(did, n)

    # -- Column helpers -------------------------------------------------------

    def get_common_columns(self, ids=None):
        """Return the list of column names shared by all specified (or all loaded) datasets.

        Args:
            ids: List of dataset IDs to compare; None compares all loaded datasets.

        Returns:
            A list of column name strings common to all specified datasets.
        """
        return self._datasets_mgr.get_common_columns(ids)

    def get_numeric_columns(self, did):
        """Return the list of numeric column names for the specified dataset.

        Args:
            did: Dataset ID string.

        Returns:
            A list of column names whose Polars dtype is numeric.
        """
        return self._datasets_mgr.get_numeric_columns(did)

    # -- Load / remove --------------------------------------------------------

    def load_dataset(self, path, name=None, dataset_id=None, **kw):
        """Load a file as a new dataset, clearing the cache first.

        Args:
            path: Path to the file to load.
            name: Human-readable name for the dataset; defaults to the file's basename.
            dataset_id: Explicit ID string; auto-generated if not provided.
            **kw: Additional keyword arguments forwarded to the dataset manager loader.

        Returns:
            The dataset ID string if loading succeeded, or None on failure.
        """
        self._clear_cache()
        return self._datasets_mgr.load_dataset(path, name, dataset_id, **kw)

    def load_dataset_from_dataframe(self, df, name="Untitled", dataset_id=None, source_path=None):
        """DataFrame을 직접 데이터셋으로 로드한다."""
        self._clear_cache()
        result = self._datasets_mgr.load_dataset_from_dataframe(
            df, name=name, dataset_id=dataset_id, source_path=source_path
        )
        if result:
            self._sync_active_dataset()
        return result

    def remove_dataset(self, dataset_id):
        """Remove the specified dataset, then sync the loader to the new active dataset.

        Args:
            dataset_id: ID string of the dataset to remove.

        Returns:
            True if the dataset was found and removed, False otherwise.
        """
        self._clear_cache()
        result = self._datasets_mgr.remove_dataset(dataset_id)
        active = self._datasets_mgr.active_dataset
        if active:
            self._loader._df, self._loader._lazy_df = active.df, active.lazy_df
            self._loader._source, self._loader._profile = active.source, active.profile
        elif not self._datasets_mgr.datasets:
            self._loader._df = self._loader._lazy_df = None
            self._loader._source = self._loader._profile = None
        return result

    def activate_dataset(self, dataset_id):
        """Set the specified dataset as active and sync the loader's state to it.

        Args:
            dataset_id: ID string of the dataset to activate.

        Returns:
            True if activation succeeded, False if the dataset ID was not found.
        """
        self._clear_cache()
        result = self._datasets_mgr.activate_dataset(dataset_id)
        if result:
            self._sync_active_dataset()
        return result

    def _sync_active_dataset(self):
        ds = self._datasets_mgr.active_dataset
        if ds:
            self._loader._df, self._loader._lazy_df = ds.df, ds.lazy_df
            self._loader._source, self._loader._profile = ds.source, ds.profile

    def clear_all_datasets(self):
        """Remove all datasets and reset the loader's state to an empty state."""
        self._clear_cache()
        self._datasets_mgr.clear_all_datasets()
        self._loader._df = self._loader._lazy_df = None
        self._loader._source = self._loader._profile = None
