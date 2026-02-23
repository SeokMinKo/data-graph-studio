"""
DataExporter — 데이터 내보내기 모듈 (stateless)

DataFrame을 인자로 받아 CSV, Excel, Parquet 형식으로 내보낸다.
"""

import logging
from typing import Optional, List

import polars as pl

from .exceptions import ExportError

logger = logging.getLogger(__name__)


class DataExporter:
    """Stateless 데이터 내보내기 클래스."""

    def export_csv(
        self,
        df: pl.DataFrame,
        path: str,
        selected_rows: Optional[List[int]] = None,
    ) -> None:
        """DataFrame을 CSV로 내보낸다.

        Args:
            df: 내보낼 DataFrame.
            path: 저장 경로.
            selected_rows: 선택된 행 인덱스 목록 (None이면 전체).

        Raises:
            ExportError: df가 None인 경우.
        """
        if df is None:
            raise ExportError(
                "No DataFrame to export",
                operation="export_csv",
                context={"path": path},
            )

        target = df[selected_rows] if selected_rows is not None else df
        target.write_csv(path)
        logger.info("data_exporter.exported_csv", extra={"row_count": len(target), "path": path})

    def export_excel(
        self,
        df: pl.DataFrame,
        path: str,
        selected_rows: Optional[List[int]] = None,
    ) -> None:
        """DataFrame을 Excel로 내보낸다.

        Args:
            df: 내보낼 DataFrame.
            path: 저장 경로.
            selected_rows: 선택된 행 인덱스 목록 (None이면 전체).

        Raises:
            ExportError: df가 None인 경우.
        """
        if df is None:
            raise ExportError(
                "No DataFrame to export",
                operation="export_excel",
                context={"path": path},
            )

        target = df[selected_rows] if selected_rows is not None else df
        target.write_excel(path)
        logger.info("data_exporter.exported_excel", extra={"row_count": len(target), "path": path})

    def export_parquet(
        self,
        df: pl.DataFrame,
        path: str,
        selected_rows: Optional[List[int]] = None,
    ) -> None:
        """DataFrame을 Parquet으로 내보낸다.

        Args:
            df: 내보낼 DataFrame.
            path: 저장 경로.
            selected_rows: 선택된 행 인덱스 목록 (None이면 전체).

        Raises:
            ExportError: df가 None인 경우.
        """
        if df is None:
            raise ExportError(
                "No DataFrame to export",
                operation="export_parquet",
                context={"path": path},
            )

        target = df[selected_rows] if selected_rows is not None else df
        target.write_parquet(path)
        logger.info("data_exporter.exported_parquet", extra={"row_count": len(target), "path": path})
