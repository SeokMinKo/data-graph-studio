"""
DatasetMixin — multi-dataset management delegation methods.

Extracted from DataEngine to reduce god-object complexity.
All methods delegate to self._datasets_mgr and self._loader,
which are initialised by DataEngine.__init__.
"""



class DatasetMixin(object):
    """Mixin for multi-dataset management methods.

    Delegates all dataset operations to self._datasets_mgr (DatasetManager)
    and keeps self._loader in sync whenever the active dataset changes.

    Requires the host class to provide:
        self._datasets_mgr  — DatasetManager instance
        self._loader        — FileLoader instance
        self._clear_cache() — cache invalidation method
    """

    # -- DatasetManager: class-level constants (via properties) ---------------

    @property
    def MAX_DATASETS(self):
        """Maximum number of datasets that can be loaded simultaneously.

        Output: int — hard limit enforced by DatasetManager
        """
        return self._datasets_mgr.MAX_DATASETS

    @property
    def MAX_TOTAL_MEMORY(self):
        """Maximum combined memory in bytes allowed across all loaded datasets.

        Output: int — byte threshold enforced by DatasetManager
        """
        return self._datasets_mgr.MAX_TOTAL_MEMORY

    @property
    def DEFAULT_COLORS(self):
        """Ordered list of default hex color strings assigned to new datasets.

        Output: List[str] — hex color strings cycled through on each new load
        """
        return self._datasets_mgr.DEFAULT_COLORS

    # -- Properties -----------------------------------------------------------

    @property
    def datasets(self):
        """Ordered mapping of dataset ID to DatasetInfo for all loaded datasets.

        Output: dict[str, DatasetInfo] — insertion-ordered; empty when nothing is loaded
        """
        return self._datasets_mgr.datasets

    @property
    def _datasets(self):
        return self._datasets_mgr.datasets

    @property
    def dataset_count(self):
        """Number of datasets currently held in the dataset manager.

        Output: int >= 0
        """
        return self._datasets_mgr.dataset_count

    @property
    def active_dataset_id(self):
        """ID of the currently active dataset, or None if no dataset is active.

        Output: str or None
        """
        return self._datasets_mgr.active_dataset_id

    @property
    def _active_dataset_id(self):
        return self._datasets_mgr._active_dataset_id

    @_active_dataset_id.setter
    def _active_dataset_id(self, value):
        self._datasets_mgr._active_dataset_id = value

    @property
    def active_dataset(self):
        """DatasetInfo for the currently active dataset, or None if no dataset is active.

        Output: DatasetInfo or None
        """
        return self._datasets_mgr.active_dataset

    @property
    def _color_index(self):
        return self._datasets_mgr._color_index

    @_color_index.setter
    def _color_index(self, value):
        self._datasets_mgr._color_index = value

    # -- Lookup ---------------------------------------------------------------

    def get_dataset(self, did):
        """Return the DatasetInfo for the given dataset ID, or None if not found.

        Input: did — str, dataset ID to look up
        Output: DatasetInfo or None
        """
        return self._datasets_mgr.get_dataset(did)

    def get_dataset_df(self, did):
        """Return the Polars DataFrame for the given dataset ID, or None if unavailable.

        Input: did — str, dataset ID to look up
        Output: pl.DataFrame or None
        """
        return self._datasets_mgr.get_dataset_df(did)

    def list_datasets(self):
        """Return summary dicts for all loaded datasets.

        Output: List[dict] — each dict contains keys: id, name, row_count, column_count
        """
        return self._datasets_mgr.list_datasets()

    # -- Memory ---------------------------------------------------------------

    def get_total_memory_usage(self):
        """Return the combined estimated memory usage in bytes for all loaded datasets.

        Output: int — total bytes across all DatasetInfo entries
        """
        return self._datasets_mgr.get_total_memory_usage()

    def can_load_dataset(self, sz):
        """Check whether a dataset of the given byte size can be loaded within limits.

        Input: sz — int, estimated size in bytes of the dataset to be loaded
        Output: bool — True if dataset_count < MAX_DATASETS and total memory would stay under MAX_TOTAL_MEMORY
        """
        return self._datasets_mgr.can_load_dataset(sz)

    # -- Mutation -------------------------------------------------------------

    def set_dataset_color(self, did, c):
        """Assign a display color to the specified dataset.

        Input: did — str, dataset ID
        Input: c — str, hex color string (e.g. "#FF5733") or color name
        """
        self._datasets_mgr.set_dataset_color(did, c)

    def rename_dataset(self, did, n):
        """Rename the specified dataset.

        Input: did — str, dataset ID
        Input: n — str, new human-readable name for the dataset
        """
        self._datasets_mgr.rename_dataset(did, n)

    # -- Column helpers -------------------------------------------------------

    def get_common_columns(self, ids=None):
        """Return column names shared by all specified (or all loaded) datasets.

        Input: ids — List[str] or None; None compares all currently loaded datasets
        Output: List[str] — column names present in every specified dataset
        """
        return self._datasets_mgr.get_common_columns(ids)

    def get_numeric_columns(self, did):
        """Return the list of numeric column names for the specified dataset.

        Input: did — str, dataset ID
        Output: List[str] — column names whose Polars dtype is numeric
        """
        return self._datasets_mgr.get_numeric_columns(did)

    # -- Load / remove --------------------------------------------------------

    def load_dataset(self, path, name=None, dataset_id=None, **kw):
        """Load a file as a new dataset, clearing the engine cache first.

        Input: path — str or Path, file path to load
        Input: name — str or None, human-readable label; defaults to file basename
        Input: dataset_id — str or None, explicit ID; auto-generated if None
        Input: **kw — additional keyword arguments forwarded to DatasetManager
        Output: str dataset_id if loading succeeded, or None on failure
        Invariants: self._clear_cache() is called unconditionally before loading
        """
        self._clear_cache()
        return self._datasets_mgr.load_dataset(path, name, dataset_id, **kw)

    def load_dataset_from_dataframe(self, df, name="Untitled", dataset_id=None, source_path=None):
        """Load a Polars DataFrame directly as a new dataset and sync the active dataset.

        Input: df — pl.DataFrame, the data to load
        Input: name — str, display name for the dataset (default "Untitled")
        Input: dataset_id — str or None, explicit ID; auto-generated if None
        Input: source_path — str or None, optional file path for provenance tracking
        Output: str dataset_id if loading succeeded, or None on failure
        Invariants: clears cache first; calls _sync_active_dataset() on success
        """
        self._clear_cache()
        result = self._datasets_mgr.load_dataset_from_dataframe(
            df, name=name, dataset_id=dataset_id, source_path=source_path
        )
        if result:
            self._sync_active_dataset()
        return result

    def remove_dataset(self, dataset_id):
        """Remove the specified dataset and sync the loader to the new active dataset.

        Input: dataset_id — str, ID of the dataset to remove
        Output: bool — True if the dataset was found and removed, False otherwise
        Invariants: clears cache first; if no datasets remain, loader state is set to None
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
        """Set the specified dataset as active and sync the loader's internal state.

        Input: dataset_id — str, ID of the dataset to activate
        Output: bool — True if activation succeeded, False if dataset_id not found
        Invariants: clears cache first; calls _sync_active_dataset() on success
        """
        self._clear_cache()
        result = self._datasets_mgr.activate_dataset(dataset_id)
        if result:
            self._sync_active_dataset()
        return result

    def _sync_active_dataset(self):
        """Synchronise the loader's internal references to the currently active dataset.

        Invariants: called after any operation that changes the active dataset;
                    no-op if active_dataset is None
        """
        ds = self._datasets_mgr.active_dataset
        if ds:
            self._loader._df, self._loader._lazy_df = ds.df, ds.lazy_df
            self._loader._source, self._loader._profile = ds.source, ds.profile

    def clear_all_datasets(self):
        """Remove all datasets and reset the loader's state to an empty baseline.

        Invariants: clears cache first; after this call dataset_count == 0 and loader holds no data
        """
        self._clear_cache()
        self._datasets_mgr.clear_all_datasets()
        self._loader._df = self._loader._lazy_df = None
        self._loader._source = self._loader._profile = None
