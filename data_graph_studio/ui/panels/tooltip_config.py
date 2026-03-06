"""
Tooltip Configuration - Spotfire 스타일 툴팁 설정

시각화 툴팁의 내용과 형식을 설정합니다.
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field


@dataclass
class TooltipItem:
    """툴팁 항목"""

    column: str
    display_name: Optional[str] = None
    format_string: Optional[str] = None
    visible: bool = True
    order: int = 0

    def __post_init__(self):
        if self.display_name is None:
            self.display_name = self.column

    def format_value(self, value: Any) -> str:
        """값 포맷팅"""
        if value is None:
            return ""

        if self.format_string:
            try:
                return self.format_string.format(value=value)
            except (ValueError, KeyError):
                return str(value)

        return str(value)


@dataclass
class TooltipConfig:
    """
    툴팁 설정

    툴팁에 표시할 항목과 형식을 정의합니다.
    """

    enabled: bool = True
    items: List[TooltipItem] = field(default_factory=list)

    # 스타일
    background_color: str = "#323D4A"
    text_color: str = "#000000"
    border_color: str = "#CCCCCC"
    font_size: int = 10
    padding: int = 8
    border_radius: int = 4

    # 고급 설정
    show_column_names: bool = True
    separator: str = ": "
    line_separator: str = "\n"
    max_width: int = 300

    # 커스텀 템플릿
    template: Optional[str] = None

    def add_item(self, item: TooltipItem) -> None:
        """항목 추가"""
        self.items.append(item)
        self._sort_items()

    def remove_item(self, column: str) -> None:
        """항목 제거"""
        self.items = [i for i in self.items if i.column != column]

    def get_item(self, column: str) -> Optional[TooltipItem]:
        """항목 조회"""
        for item in self.items:
            if item.column == column:
                return item
        return None

    def set_item_order(self, column: str, order: int) -> None:
        """항목 순서 설정"""
        item = self.get_item(column)
        if item:
            item.order = order
            self._sort_items()

    def _sort_items(self) -> None:
        """항목 정렬"""
        self.items.sort(key=lambda x: x.order)

    def clear(self) -> None:
        """모든 항목 클리어"""
        self.items.clear()


class TooltipFormatter:
    """
    툴팁 포맷터

    툴팁 텍스트를 생성합니다.
    """

    def __init__(self, config: TooltipConfig):
        self.config = config

    def format(self, data: Dict[str, Any]) -> str:
        """
        툴팁 텍스트 생성

        Args:
            data: {컬럼: 값} 딕셔너리

        Returns:
            포맷된 툴팁 텍스트
        """
        if not self.config.enabled:
            return ""

        # 커스텀 템플릿 사용
        if self.config.template:
            try:
                return self.config.template.format(**data)
            except (KeyError, ValueError):
                pass

        # 기본 포맷
        lines = []

        for item in self.config.items:
            if not item.visible:
                continue

            if item.column not in data:
                continue

            value = data[item.column]
            formatted_value = item.format_value(value)

            if self.config.show_column_names:
                line = f"{item.display_name}{self.config.separator}{formatted_value}"
            else:
                line = formatted_value

            lines.append(line)

        return self.config.line_separator.join(lines)

    def format_html(self, data: Dict[str, Any]) -> str:
        """
        HTML 형식의 툴팁 생성

        Args:
            data: {컬럼: 값} 딕셔너리

        Returns:
            HTML 포맷 툴팁
        """
        if not self.config.enabled:
            return ""

        style = f"""
        <div style="
            background-color: {self.config.background_color};
            color: {self.config.text_color};
            border: 1px solid {self.config.border_color};
            border-radius: {self.config.border_radius}px;
            padding: {self.config.padding}px;
            font-size: {self.config.font_size}px;
            max-width: {self.config.max_width}px;
        ">
        """

        rows = []
        for item in self.config.items:
            if not item.visible:
                continue

            if item.column not in data:
                continue

            value = data[item.column]
            formatted_value = item.format_value(value)

            if self.config.show_column_names:
                row = f"<tr><td><b>{item.display_name}</b></td><td>{formatted_value}</td></tr>"
            else:
                row = f"<tr><td>{formatted_value}</td></tr>"

            rows.append(row)

        table = f"<table>{''.join(rows)}</table>"

        return f"{style}{table}</div>"


class TooltipBuilder:
    """
    툴팁 빌더

    툴팁 설정을 쉽게 생성하기 위한 빌더 패턴입니다.
    """

    def __init__(self):
        self._config = TooltipConfig()
        self._order = 0

    def add_column(
        self,
        column: str,
        display_name: Optional[str] = None,
        format_string: Optional[str] = None,
    ) -> "TooltipBuilder":
        """컬럼 추가"""
        item = TooltipItem(
            column=column,
            display_name=display_name,
            format_string=format_string,
            order=self._order,
        )
        self._config.add_item(item)
        self._order += 1
        return self

    def set_style(
        self,
        background_color: Optional[str] = None,
        text_color: Optional[str] = None,
        border_color: Optional[str] = None,
        font_size: Optional[int] = None,
    ) -> "TooltipBuilder":
        """스타일 설정"""
        if background_color:
            self._config.background_color = background_color
        if text_color:
            self._config.text_color = text_color
        if border_color:
            self._config.border_color = border_color
        if font_size:
            self._config.font_size = font_size
        return self

    def set_template(self, template: str) -> "TooltipBuilder":
        """커스텀 템플릿 설정"""
        self._config.template = template
        return self

    def hide_column_names(self) -> "TooltipBuilder":
        """컬럼 이름 숨기기"""
        self._config.show_column_names = False
        return self

    def build(self) -> TooltipConfig:
        """설정 반환"""
        return self._config
