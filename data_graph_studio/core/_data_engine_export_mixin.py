"""DataEngine export mixin — DataExporter delegation."""

from __future__ import annotations


class _DataEngineExportMixin:
    """CSV / Excel / Parquet export methods for DataEngine.

    Attributes accessed from DataEngine:
        _exporter: DataExporter instance.
        df: active DataFrame property.
    """

    def export_csv(self, path, selected_rows=None) -> None:
        """Export the active DataFrame (or a row subset) to a CSV file.

        Input:
            path: Destination filesystem path string for the output CSV file.
            selected_rows: Optional list of zero-based row indices to export; if None,
                all rows are exported.

        Output:
            None. Side effect: CSV file is written to path.

        Raises:
            ExportError: if the file cannot be written.

        Invariants:
            - No-op if no data is loaded.
            - Exported column set matches the active DataFrame.
        """
        if self.df is not None:
            self._exporter.export_csv(self.df, path, selected_rows)

    def export_excel(self, path, selected_rows=None) -> None:
        """Export the active DataFrame (or a row subset) to an Excel (.xlsx) file.

        Input:
            path: Destination filesystem path string for the output .xlsx file.
            selected_rows: Optional list of zero-based row indices to export; if None,
                all rows are exported.

        Output:
            None. Side effect: Excel file is written to path.

        Raises:
            ExportError: if the file cannot be written or openpyxl is not installed.

        Invariants:
            - No-op if no data is loaded.
            - Exported column set matches the active DataFrame.
        """
        if self.df is not None:
            self._exporter.export_excel(self.df, path, selected_rows)

    def export_parquet(self, path, selected_rows=None) -> None:
        """Export the active DataFrame (or a row subset) to a Parquet file.

        Input:
            path: Destination filesystem path string for the output .parquet file.
            selected_rows: Optional list of zero-based row indices to export; if None,
                all rows are exported.

        Output:
            None. Side effect: Parquet file is written to path.

        Raises:
            ExportError: if the file cannot be written.

        Invariants:
            - No-op if no data is loaded.
            - Exported column set matches the active DataFrame.
        """
        if self.df is not None:
            self._exporter.export_parquet(self.df, path, selected_rows)
