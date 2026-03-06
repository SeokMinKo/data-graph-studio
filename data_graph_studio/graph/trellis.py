"""
Trellis Visualization - Spotfire 스타일 트렐리스 시각화

하나의 시각화를 여러 패널로 분할하여 카테고리별 비교를 가능하게 합니다.
"""

from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import polars as pl
import math


class TrellisMode(Enum):
    """트렐리스 모드"""

    ROWS_AND_COLUMNS = "rows_columns"  # 행과 열로 분할
    PANELS = "panels"  # 페이지 형태로 분할


@dataclass
class TrellisSettings:
    """트렐리스 설정"""

    enabled: bool = False
    mode: TrellisMode = TrellisMode.ROWS_AND_COLUMNS

    # Rows and Columns 모드
    row_column: Optional[str] = None
    col_column: Optional[str] = None
    max_rows: int = 5
    max_cols: int = 5

    # Panels 모드
    panel_column: Optional[str] = None
    panels_per_page: int = 4

    # 공통 옵션
    sync_axes: bool = True
    show_empty_panels: bool = True
    panel_spacing: float = 0.02  # 패널 간 간격 (비율)
    show_panel_labels: bool = True


@dataclass
class TrellisPanel:
    """트렐리스 패널"""

    row_idx: int
    col_idx: int
    row_value: Any
    col_value: Any
    data: pl.DataFrame
    x: float = 0
    y: float = 0
    width: float = 0
    height: float = 0
    label: str = ""


@dataclass
class TrellisLayout:
    """트렐리스 레이아웃"""

    n_rows: int
    n_cols: int
    panels: List[Dict[str, Any]]
    row_values: List[Any]
    col_values: List[Any]

    # 축 동기화
    sync_axes: bool = True
    shared_x_range: Optional[Tuple[float, float]] = None
    shared_y_range: Optional[Tuple[float, float]] = None

    # Panels 모드용
    total_panels: int = 0
    panels_per_page: int = 4
    total_pages: int = 1
    current_page: int = 0


class TrellisCalculator:
    """
    트렐리스 계산기

    데이터를 패널로 분할하고 레이아웃을 계산합니다.
    """

    def calculate(
        self,
        data: pl.DataFrame,
        settings: TrellisSettings,
        total_width: float = 100,
        total_height: float = 100,
        value_column: Optional[str] = None,
    ) -> TrellisLayout:
        """
        트렐리스 레이아웃 계산

        Args:
            data: 데이터프레임
            settings: 트렐리스 설정
            total_width: 전체 너비
            total_height: 전체 높이
            value_column: 축 범위 계산용 값 컬럼

        Returns:
            트렐리스 레이아웃
        """
        if not settings.enabled:
            # 트렐리스 비활성화 - 단일 패널
            return TrellisLayout(
                n_rows=1,
                n_cols=1,
                panels=[
                    {
                        "row_idx": 0,
                        "col_idx": 0,
                        "row_value": None,
                        "col_value": None,
                        "data": data,
                        "x": 0,
                        "y": 0,
                        "width": total_width,
                        "height": total_height,
                        "label": "",
                    }
                ],
                row_values=[None],
                col_values=[None],
                sync_axes=settings.sync_axes,
            )

        if settings.mode == TrellisMode.ROWS_AND_COLUMNS:
            return self._calculate_rows_and_columns(
                data, settings, total_width, total_height, value_column
            )
        else:
            return self._calculate_panels(
                data, settings, total_width, total_height, value_column
            )

    def _calculate_rows_and_columns(
        self,
        data: pl.DataFrame,
        settings: TrellisSettings,
        total_width: float,
        total_height: float,
        value_column: Optional[str],
    ) -> TrellisLayout:
        """Rows and Columns 모드 계산"""

        # 행/열 고유값 추출
        if settings.row_column and settings.row_column in data.columns:
            row_values = data[settings.row_column].unique().sort().to_list()
            row_values = row_values[: settings.max_rows]
        else:
            row_values = [None]

        if settings.col_column and settings.col_column in data.columns:
            col_values = data[settings.col_column].unique().sort().to_list()
            col_values = col_values[: settings.max_cols]
        else:
            col_values = [None]

        n_rows = len(row_values)
        n_cols = len(col_values)

        # 패널 크기 계산
        spacing = settings.panel_spacing
        panel_width = (total_width * (1 - spacing * (n_cols + 1))) / n_cols
        panel_height = (total_height * (1 - spacing * (n_rows + 1))) / n_rows

        # 축 범위 계산 (동기화용)
        shared_y_range = None
        if settings.sync_axes and value_column and value_column in data.columns:
            values = data[value_column].drop_nulls()
            if len(values) > 0:
                shared_y_range = (values.min(), values.max())

        # 패널 생성
        panels = []
        for row_idx, row_val in enumerate(row_values):
            for col_idx, col_val in enumerate(col_values):
                # 데이터 필터링
                panel_data = data

                if settings.row_column and row_val is not None:
                    panel_data = panel_data.filter(
                        pl.col(settings.row_column) == row_val
                    )

                if settings.col_column and col_val is not None:
                    panel_data = panel_data.filter(
                        pl.col(settings.col_column) == col_val
                    )

                # 빈 패널 처리
                if len(panel_data) == 0 and not settings.show_empty_panels:
                    continue

                # 좌표 계산
                x = total_width * spacing + col_idx * (
                    panel_width + total_width * spacing
                )
                y = total_height * spacing + row_idx * (
                    panel_height + total_height * spacing
                )

                # 레이블
                label_parts = []
                if row_val is not None:
                    label_parts.append(f"{settings.row_column}={row_val}")
                if col_val is not None:
                    label_parts.append(f"{settings.col_column}={col_val}")
                label = ", ".join(label_parts)

                panels.append(
                    {
                        "row_idx": row_idx,
                        "col_idx": col_idx,
                        "row_value": row_val,
                        "col_value": col_val,
                        "data": panel_data,
                        "x": x,
                        "y": y,
                        "width": panel_width,
                        "height": panel_height,
                        "label": label,
                    }
                )

        return TrellisLayout(
            n_rows=n_rows,
            n_cols=n_cols,
            panels=panels,
            row_values=row_values,
            col_values=col_values,
            sync_axes=settings.sync_axes,
            shared_y_range=shared_y_range,
            total_panels=len(panels),
        )

    def _calculate_panels(
        self,
        data: pl.DataFrame,
        settings: TrellisSettings,
        total_width: float,
        total_height: float,
        value_column: Optional[str],
    ) -> TrellisLayout:
        """Panels 모드 계산 (페이지네이션)"""

        if not settings.panel_column or settings.panel_column not in data.columns:
            return self._calculate_rows_and_columns(
                data,
                TrellisSettings(enabled=False),
                total_width,
                total_height,
                value_column,
            )

        # 패널 값 추출
        panel_values = data[settings.panel_column].unique().sort().to_list()
        total_panels = len(panel_values)
        panels_per_page = max(1, settings.panels_per_page)  # Ensure at least 1
        total_pages = (
            math.ceil(total_panels / panels_per_page) if total_panels > 0 else 1
        )

        # 그리드 계산 (정사각형에 가깝게)
        n_cols = math.ceil(math.sqrt(panels_per_page))
        n_rows = math.ceil(panels_per_page / n_cols)

        # 패널 크기
        spacing = settings.panel_spacing
        panel_width = (total_width * (1 - spacing * (n_cols + 1))) / n_cols
        panel_height = (total_height * (1 - spacing * (n_rows + 1))) / n_rows

        # 축 범위 계산
        shared_y_range = None
        if settings.sync_axes and value_column and value_column in data.columns:
            values = data[value_column].drop_nulls()
            if len(values) > 0:
                shared_y_range = (values.min(), values.max())

        # 패널 생성 (현재 페이지만)
        panels = []
        for idx, panel_val in enumerate(panel_values):
            row_idx = idx // n_cols
            col_idx = idx % n_cols

            # 데이터 필터링
            panel_data = data.filter(pl.col(settings.panel_column) == panel_val)

            if len(panel_data) == 0 and not settings.show_empty_panels:
                continue

            # 좌표
            x = total_width * spacing + col_idx * (panel_width + total_width * spacing)
            y = total_height * spacing + row_idx * (
                panel_height + total_height * spacing
            )

            panels.append(
                {
                    "row_idx": row_idx,
                    "col_idx": col_idx,
                    "row_value": None,
                    "col_value": None,
                    "panel_value": panel_val,
                    "data": panel_data,
                    "x": x,
                    "y": y,
                    "width": panel_width,
                    "height": panel_height,
                    "label": f"{settings.panel_column}={panel_val}",
                }
            )

        return TrellisLayout(
            n_rows=n_rows,
            n_cols=n_cols,
            panels=panels,
            row_values=[],
            col_values=[],
            sync_axes=settings.sync_axes,
            shared_y_range=shared_y_range,
            total_panels=total_panels,
            panels_per_page=panels_per_page,
            total_pages=total_pages,
        )

    def get_panel_data(
        self, layout: TrellisLayout, row_idx: int, col_idx: int
    ) -> Optional[pl.DataFrame]:
        """특정 패널의 데이터 반환"""
        for panel in layout.panels:
            if panel["row_idx"] == row_idx and panel["col_idx"] == col_idx:
                return panel["data"]
        return None

    def get_panel_bounds(
        self, layout: TrellisLayout, row_idx: int, col_idx: int
    ) -> Optional[Dict[str, float]]:
        """특정 패널의 경계 반환"""
        for panel in layout.panels:
            if panel["row_idx"] == row_idx and panel["col_idx"] == col_idx:
                return {
                    "x": panel["x"],
                    "y": panel["y"],
                    "width": panel["width"],
                    "height": panel["height"],
                }
        return None
