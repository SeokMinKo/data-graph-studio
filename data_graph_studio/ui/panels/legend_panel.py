"""
Legend Panel - Spotfire 스타일 범례 설정

시각화 범례의 위치, 스타일, 내용을 설정합니다.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum


class LegendPosition(Enum):
    """범례 위치"""
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    FLOATING = "floating"
    NONE = "none"


class LegendStyle(Enum):
    """범례 스타일"""
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"
    GRID = "grid"


@dataclass
class LegendItem:
    """범례 항목"""
    label: str
    color: str
    visible: bool = True
    symbol: str = "square"  # square, circle, line, triangle
    line_style: Optional[str] = None  # solid, dashed, dotted


@dataclass
class LegendConfig:
    """
    범례 설정

    시각화 범례의 외관과 동작을 정의합니다.
    """
    visible: bool = True
    position: LegendPosition = LegendPosition.RIGHT
    style: LegendStyle = LegendStyle.VERTICAL

    # 제목
    title: str = ""
    show_title: bool = True

    # 크기
    max_width: int = 200
    max_height: int = 400

    # 스타일
    background_color: str = "#323D4A"
    background_opacity: float = 0.9
    border_color: str = "#CCCCCC"
    border_width: int = 1
    border_radius: int = 4
    padding: int = 8

    # 폰트
    font_family: str = "Arial"
    font_size: int = 10
    font_color: str = "#333333"
    title_font_size: int = 12
    title_font_bold: bool = True

    # 아이템 스타일
    item_spacing: int = 4
    symbol_size: int = 12
    symbol_spacing: int = 8

    # 플로팅 위치 (position이 FLOATING일 때)
    floating_x: int = 10
    floating_y: int = 10

    # 항목
    items: List[LegendItem] = field(default_factory=list)

    # 동작
    interactive: bool = True  # 클릭으로 시리즈 토글 가능
    show_all_button: bool = False
    hide_all_button: bool = False

    def add_item(self, item: LegendItem) -> None:
        """항목 추가"""
        self.items.append(item)

    def remove_item(self, label: str) -> None:
        """항목 제거"""
        self.items = [i for i in self.items if i.label != label]

    def get_item(self, label: str) -> Optional[LegendItem]:
        """항목 조회"""
        for item in self.items:
            if item.label == label:
                return item
        return None

    def toggle_item(self, label: str) -> None:
        """항목 토글"""
        item = self.get_item(label)
        if item:
            item.visible = not item.visible

    def show_all(self) -> None:
        """모든 항목 표시"""
        for item in self.items:
            item.visible = True

    def hide_all(self) -> None:
        """모든 항목 숨김"""
        for item in self.items:
            item.visible = False

    def get_visible_items(self) -> List[LegendItem]:
        """가시적인 항목 목록"""
        return [i for i in self.items if i.visible]

    def clear(self) -> None:
        """모든 항목 클리어"""
        self.items.clear()


class LegendRenderer:
    """
    범례 렌더러

    범례를 렌더링하기 위한 헬퍼 클래스입니다.
    """

    def __init__(self, config: LegendConfig):
        self.config = config

    def get_position_offset(
        self,
        chart_width: int,
        chart_height: int,
        legend_width: int,
        legend_height: int
    ) -> tuple:
        """
        범례 위치 오프셋 계산

        Args:
            chart_width: 차트 너비
            chart_height: 차트 높이
            legend_width: 범례 너비
            legend_height: 범례 높이

        Returns:
            (x, y) 오프셋
        """
        pos = self.config.position
        padding = 10

        if pos == LegendPosition.TOP:
            return ((chart_width - legend_width) // 2, padding)

        elif pos == LegendPosition.BOTTOM:
            return ((chart_width - legend_width) // 2, chart_height - legend_height - padding)

        elif pos == LegendPosition.LEFT:
            return (padding, (chart_height - legend_height) // 2)

        elif pos == LegendPosition.RIGHT:
            return (chart_width - legend_width - padding, (chart_height - legend_height) // 2)

        elif pos == LegendPosition.TOP_LEFT:
            return (padding, padding)

        elif pos == LegendPosition.TOP_RIGHT:
            return (chart_width - legend_width - padding, padding)

        elif pos == LegendPosition.BOTTOM_LEFT:
            return (padding, chart_height - legend_height - padding)

        elif pos == LegendPosition.BOTTOM_RIGHT:
            return (chart_width - legend_width - padding, chart_height - legend_height - padding)

        elif pos == LegendPosition.FLOATING:
            return (self.config.floating_x, self.config.floating_y)

        return (0, 0)

    def calculate_size(self) -> tuple:
        """
        범례 크기 계산

        Returns:
            (width, height)
        """
        if not self.config.visible or not self.config.items:
            return (0, 0)

        visible_items = self.config.get_visible_items()
        if not visible_items:
            return (0, 0)

        # 항목 수 기반 계산
        item_count = len(visible_items)
        item_height = self.config.symbol_size + self.config.item_spacing

        if self.config.style == LegendStyle.VERTICAL:
            height = item_count * item_height + 2 * self.config.padding
            if self.config.show_title and self.config.title:
                height += self.config.title_font_size + self.config.item_spacing
            width = self.config.max_width

        elif self.config.style == LegendStyle.HORIZONTAL:
            # 가로 배치
            width = min(
                sum(len(i.label) * 8 + self.config.symbol_size + self.config.symbol_spacing
                    for i in visible_items) + 2 * self.config.padding,
                self.config.max_width
            )
            height = item_height + 2 * self.config.padding
            if self.config.show_title and self.config.title:
                height += self.config.title_font_size + self.config.item_spacing

        else:  # GRID
            cols = 2
            rows = (item_count + cols - 1) // cols
            width = self.config.max_width
            height = rows * item_height + 2 * self.config.padding

        return (
            min(width, self.config.max_width),
            min(height, self.config.max_height)
        )

    def render_to_html(self) -> str:
        """
        HTML로 렌더링

        Returns:
            HTML 문자열
        """
        if not self.config.visible:
            return ""

        visible_items = self.config.get_visible_items()
        if not visible_items:
            return ""

        style = f"""
        background-color: rgba({self._hex_to_rgb(self.config.background_color)}, {self.config.background_opacity});
        border: {self.config.border_width}px solid {self.config.border_color};
        border-radius: {self.config.border_radius}px;
        padding: {self.config.padding}px;
        font-family: {self.config.font_family};
        font-size: {self.config.font_size}px;
        color: {self.config.font_color};
        max-width: {self.config.max_width}px;
        """

        html = f'<div style="{style}">'

        # 제목
        if self.config.show_title and self.config.title:
            title_style = f"font-size: {self.config.title_font_size}px;"
            if self.config.title_font_bold:
                title_style += " font-weight: bold;"
            html += f'<div style="{title_style}">{self.config.title}</div>'

        # 항목
        for item in visible_items:
            item_html = self._render_item_html(item)
            html += item_html

        html += '</div>'

        return html

    def _render_item_html(self, item: LegendItem) -> str:
        """항목 HTML 렌더링"""
        symbol = self._get_symbol_svg(item.symbol, item.color, self.config.symbol_size)

        return f"""
        <div style="display: flex; align-items: center; margin: {self.config.item_spacing}px 0;">
            {symbol}
            <span style="margin-left: {self.config.symbol_spacing}px;">{item.label}</span>
        </div>
        """

    def _get_symbol_svg(self, symbol: str, color: str, size: int) -> str:
        """심볼 SVG"""
        half = size // 2

        if symbol == "square":
            return f'<svg width="{size}" height="{size}"><rect width="{size}" height="{size}" fill="{color}"/></svg>'
        elif symbol == "circle":
            return f'<svg width="{size}" height="{size}"><circle cx="{half}" cy="{half}" r="{half}" fill="{color}"/></svg>'
        elif symbol == "line":
            return f'<svg width="{size}" height="{size}"><line x1="0" y1="{half}" x2="{size}" y2="{half}" stroke="{color}" stroke-width="2"/></svg>'
        elif symbol == "triangle":
            return f'<svg width="{size}" height="{size}"><polygon points="{half},0 0,{size} {size},{size}" fill="{color}"/></svg>'

        return ""

    def _hex_to_rgb(self, hex_color: str) -> str:
        """HEX를 RGB로 변환"""
        hex_color = hex_color.lstrip('#')
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return f"{r}, {g}, {b}"


class LegendBuilder:
    """
    범례 빌더

    범례 설정을 쉽게 생성하기 위한 빌더 패턴입니다.
    """

    def __init__(self):
        self._config = LegendConfig()

    def set_position(self, position: LegendPosition) -> 'LegendBuilder':
        """위치 설정"""
        self._config.position = position
        return self

    def set_style(self, style: LegendStyle) -> 'LegendBuilder':
        """스타일 설정"""
        self._config.style = style
        return self

    def set_title(self, title: str) -> 'LegendBuilder':
        """제목 설정"""
        self._config.title = title
        self._config.show_title = True
        return self

    def add_item(
        self,
        label: str,
        color: str,
        symbol: str = "square"
    ) -> 'LegendBuilder':
        """항목 추가"""
        self._config.add_item(LegendItem(
            label=label,
            color=color,
            symbol=symbol
        ))
        return self

    def set_interactive(self, interactive: bool) -> 'LegendBuilder':
        """인터랙티브 설정"""
        self._config.interactive = interactive
        return self

    def hide(self) -> 'LegendBuilder':
        """숨기기"""
        self._config.visible = False
        return self

    def build(self) -> LegendConfig:
        """설정 반환"""
        return self._config
