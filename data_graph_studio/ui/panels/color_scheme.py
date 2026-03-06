"""
Color Scheme - Spotfire 스타일 색상 스킴

시각화에서 사용하는 색상 팔레트와 스케일을 관리합니다.
"""

from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import colorsys


class ColorSchemeType(Enum):
    """색상 스킴 타입"""

    CATEGORICAL = "categorical"  # 범주형 (이산적)
    SEQUENTIAL = "sequential"  # 순차적 (연속적)
    DIVERGING = "diverging"  # 발산형 (양극단)
    CUSTOM = "custom"


@dataclass
class ColorScheme:
    """
    색상 스킴

    시각화에서 사용할 색상 목록을 정의합니다.
    """

    name: str
    colors: List[str]
    scheme_type: ColorSchemeType = ColorSchemeType.CATEGORICAL

    def get_color(self, index: int) -> str:
        """
        인덱스로 색상 조회 (순환)

        Args:
            index: 색상 인덱스

        Returns:
            색상 코드
        """
        if not self.colors:
            return "#000000"
        return self.colors[index % len(self.colors)]

    def get_colors(self, count: int) -> List[str]:
        """
        지정된 수의 색상 반환

        Args:
            count: 필요한 색상 수

        Returns:
            색상 목록
        """
        if count <= len(self.colors):
            return self.colors[:count]

        # 부족하면 순환
        result = []
        for i in range(count):
            result.append(self.get_color(i))
        return result

    def reverse(self) -> "ColorScheme":
        """역순 스킴 반환"""
        return ColorScheme(
            name=f"{self.name}_reversed",
            colors=list(reversed(self.colors)),
            scheme_type=self.scheme_type,
        )


@dataclass
class ColorPalette:
    """
    색상 팔레트

    여러 색상 스킴을 포함하는 팔레트입니다.
    """

    name: str
    schemes: Dict[str, ColorScheme] = field(default_factory=dict)

    def add_scheme(self, scheme: ColorScheme) -> None:
        """스킴 추가"""
        self.schemes[scheme.name] = scheme

    def get_scheme(self, name: str) -> Optional[ColorScheme]:
        """스킴 조회"""
        return self.schemes.get(name)

    def list_schemes(self) -> List[str]:
        """스킴 목록"""
        return list(self.schemes.keys())


@dataclass
class ColorScale:
    """
    색상 스케일

    연속적인 값에 대한 색상 매핑입니다.
    """

    colors: List[str]
    positions: List[float] = field(default_factory=list)
    domain: Tuple[float, float] = (0.0, 1.0)

    def __post_init__(self):
        if not self.positions:
            # 균등 분할
            n = len(self.colors)
            self.positions = [i / (n - 1) for i in range(n)]

    def interpolate(self, value: float) -> str:
        """
        값에 해당하는 색상 보간

        Args:
            value: 0~1 사이 값

        Returns:
            보간된 색상 코드
        """
        if not self.colors:
            return "#000000"

        if value <= 0:
            return self.colors[0]
        if value >= 1:
            return self.colors[-1]

        # 구간 찾기
        for i in range(len(self.positions) - 1):
            if self.positions[i] <= value <= self.positions[i + 1]:
                # 구간 내 보간
                t = (value - self.positions[i]) / (
                    self.positions[i + 1] - self.positions[i]
                )
                return self._interpolate_color(self.colors[i], self.colors[i + 1], t)

        return self.colors[-1]

    def map_value(self, value: float) -> str:
        """
        도메인 값을 색상으로 매핑

        Args:
            value: 도메인 내 값

        Returns:
            색상 코드
        """
        # 정규화
        if self.domain[1] == self.domain[0]:
            normalized = 0.5
        else:
            normalized = (value - self.domain[0]) / (self.domain[1] - self.domain[0])

        normalized = max(0, min(1, normalized))
        return self.interpolate(normalized)

    def _interpolate_color(self, color1: str, color2: str, t: float) -> str:
        """두 색상 사이 보간"""
        r1, g1, b1 = self._hex_to_rgb(color1)
        r2, g2, b2 = self._hex_to_rgb(color2)

        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)

        return self._rgb_to_hex(r, g, b)

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """HEX를 RGB로 변환"""
        hex_color = hex_color.lstrip("#")
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )

    def _rgb_to_hex(self, r: int, g: int, b: int) -> str:
        """RGB를 HEX로 변환"""
        return f"#{r:02x}{g:02x}{b:02x}"


class ColorSchemeManager:
    """
    색상 스킴 관리자

    내장 및 사용자 정의 색상 스킴을 관리합니다.
    """

    def __init__(self):
        self._schemes: Dict[str, ColorScheme] = {}
        self._scales: Dict[str, ColorScale] = {}

        self._register_builtin_schemes()
        self._register_builtin_scales()

    def _register_builtin_schemes(self) -> None:
        """내장 색상 스킴 등록"""

        # Categorical - 기본
        self._schemes["Categorical"] = ColorScheme(
            name="Categorical",
            colors=[
                "#1f77b4",
                "#ff7f0e",
                "#2ca02c",
                "#d62728",
                "#9467bd",
                "#8c564b",
                "#e377c2",
                "#7f7f7f",
                "#bcbd22",
                "#17becf",
            ],
            scheme_type=ColorSchemeType.CATEGORICAL,
        )

        # Spotfire 스타일
        self._schemes["Spotfire"] = ColorScheme(
            name="Spotfire",
            colors=[
                "#2E7D32",
                "#1565C0",
                "#C62828",
                "#F9A825",
                "#6A1B9A",
                "#00838F",
                "#D84315",
                "#558B2F",
                "#1976D2",
                "#AD1457",
            ],
            scheme_type=ColorSchemeType.CATEGORICAL,
        )

        # Pastel
        self._schemes["Pastel"] = ColorScheme(
            name="Pastel",
            colors=[
                "#AED6F1",
                "#A9DFBF",
                "#FAD7A0",
                "#F5B7B1",
                "#D7BDE2",
                "#D5DBDB",
                "#FADBD8",
                "#D1F2EB",
                "#FCF3CF",
                "#E8DAEF",
            ],
            scheme_type=ColorSchemeType.CATEGORICAL,
        )

        # Bold
        self._schemes["Bold"] = ColorScheme(
            name="Bold",
            colors=[
                "#E91E63",
                "#9C27B0",
                "#673AB7",
                "#3F51B5",
                "#2196F3",
                "#00BCD4",
                "#009688",
                "#4CAF50",
                "#FFEB3B",
                "#FF9800",
            ],
            scheme_type=ColorSchemeType.CATEGORICAL,
        )

        # Monochrome Blue
        self._schemes["Blue"] = ColorScheme(
            name="Blue",
            colors=[
                "#E3F2FD",
                "#BBDEFB",
                "#90CAF9",
                "#64B5F6",
                "#42A5F5",
                "#2196F3",
                "#1E88E5",
                "#1976D2",
                "#1565C0",
                "#0D47A1",
            ],
            scheme_type=ColorSchemeType.SEQUENTIAL,
        )

        # Monochrome Green
        self._schemes["Green"] = ColorScheme(
            name="Green",
            colors=[
                "#E8F5E9",
                "#C8E6C9",
                "#A5D6A7",
                "#81C784",
                "#66BB6A",
                "#4CAF50",
                "#43A047",
                "#388E3C",
                "#2E7D32",
                "#1B5E20",
            ],
            scheme_type=ColorSchemeType.SEQUENTIAL,
        )

        # Red-Yellow-Green (Traffic Light)
        self._schemes["RYG"] = ColorScheme(
            name="RYG",
            colors=["#D32F2F", "#FFCA28", "#388E3C"],
            scheme_type=ColorSchemeType.DIVERGING,
        )

        # Colorblind-safe RYG alternative (Red→Blue instead of Red→Green)
        self._schemes["RYB"] = ColorScheme(
            name="RYB",
            colors=["#D32F2F", "#FFCA28", "#1565C0"],
            scheme_type=ColorSchemeType.DIVERGING,
        )

        # Wong colorblind-safe palette (Nature Methods, 2011)
        self._schemes["Colorblind Safe"] = ColorScheme(
            name="Colorblind Safe",
            colors=[
                "#E69F00",  # Orange
                "#56B4E9",  # Sky Blue
                "#009E73",  # Bluish Green
                "#F0E442",  # Yellow
                "#0072B2",  # Blue
                "#D55E00",  # Vermillion
                "#CC79A7",  # Reddish Purple
                "#000000",  # Black
            ],
            scheme_type=ColorSchemeType.CATEGORICAL,
        )

        # Red-Blue Diverging
        self._schemes["RedBlue"] = ColorScheme(
            name="RedBlue",
            colors=["#B71C1C", "#FFCDD2", "#323D4A", "#BBDEFB", "#0D47A1"],
            scheme_type=ColorSchemeType.DIVERGING,
        )

    def _register_builtin_scales(self) -> None:
        """내장 색상 스케일 등록"""

        # Viridis
        self._scales["Viridis"] = ColorScale(
            colors=[
                "#440154",
                "#482878",
                "#3E4989",
                "#31688E",
                "#26828E",
                "#1F9E89",
                "#35B779",
                "#6DCD59",
                "#B4DE2C",
                "#FDE725",
            ]
        )

        # Plasma
        self._scales["Plasma"] = ColorScale(
            colors=[
                "#0D0887",
                "#5B02A3",
                "#9A179B",
                "#CB4678",
                "#EB7852",
                "#FBB32F",
                "#F0F921",
            ]
        )

        # Inferno
        self._scales["Inferno"] = ColorScale(
            colors=[
                "#000004",
                "#160B39",
                "#420A68",
                "#6A176E",
                "#932667",
                "#BC3754",
                "#DD513A",
                "#F37819",
                "#FCA50A",
                "#F0F921",
            ]
        )

        # Coolwarm
        self._scales["Coolwarm"] = ColorScale(
            colors=[
                "#3B4CC0",
                "#6688EE",
                "#AABBFF",
                "#DDDDDD",
                "#FFBBAA",
                "#EE6644",
                "#B40426",
            ]
        )

        # Heat
        self._scales["Heat"] = ColorScale(
            colors=["#FFFF00", "#FF9900", "#FF0000", "#990000", "#000000"]
        )

    def add_scheme(self, scheme: ColorScheme) -> None:
        """스킴 추가"""
        self._schemes[scheme.name] = scheme

    def remove_scheme(self, name: str) -> None:
        """스킴 제거"""
        if name in self._schemes:
            del self._schemes[name]

    def get_scheme(self, name: str) -> Optional[ColorScheme]:
        """스킴 조회"""
        return self._schemes.get(name)

    def list_schemes(self) -> List[str]:
        """스킴 목록"""
        return list(self._schemes.keys())

    def add_scale(self, name: str, scale: ColorScale) -> None:
        """스케일 추가"""
        self._scales[name] = scale

    def get_scale(self, name: str) -> Optional[ColorScale]:
        """스케일 조회"""
        return self._scales.get(name)

    def list_scales(self) -> List[str]:
        """스케일 목록"""
        return list(self._scales.keys())

    def create_sequential_scheme(
        self, name: str, base_color: str, count: int = 10
    ) -> ColorScheme:
        """
        순차적 색상 스킴 생성

        Args:
            name: 스킴 이름
            base_color: 기본 색상
            count: 색상 수

        Returns:
            생성된 색상 스킴
        """
        colors = self._generate_sequential_colors(base_color, count)
        scheme = ColorScheme(
            name=name, colors=colors, scheme_type=ColorSchemeType.SEQUENTIAL
        )
        self.add_scheme(scheme)
        return scheme

    def _generate_sequential_colors(self, base_color: str, count: int) -> List[str]:
        """순차적 색상 생성"""
        r, g, b = self._hex_to_rgb(base_color)
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)

        colors = []
        for i in range(count):
            # 밝기를 변화
            new_l = 0.1 + (0.8 * i / (count - 1)) if count > 1 else l
            new_r, new_g, new_b = colorsys.hls_to_rgb(h, new_l, s)
            colors.append(
                self._rgb_to_hex(int(new_r * 255), int(new_g * 255), int(new_b * 255))
            )

        return colors

    def _hex_to_rgb(self, hex_color: str) -> Tuple[int, int, int]:
        """HEX를 RGB로 변환"""
        hex_color = hex_color.lstrip("#")
        return (
            int(hex_color[0:2], 16),
            int(hex_color[2:4], 16),
            int(hex_color[4:6], 16),
        )

    def _rgb_to_hex(self, r: int, g: int, b: int) -> str:
        """RGB를 HEX로 변환"""
        return f"#{r:02x}{g:02x}{b:02x}"


# 기본 인스턴스
default_color_manager = ColorSchemeManager()


def get_categorical_colors(count: int, scheme: str = "Categorical") -> List[str]:
    """범주형 색상 얻기"""
    s = default_color_manager.get_scheme(scheme)
    if s:
        return s.get_colors(count)
    return ["#000000"] * count


def get_sequential_color(value: float, scale: str = "Viridis") -> str:
    """순차적 색상 얻기"""
    s = default_color_manager.get_scale(scale)
    if s:
        return s.interpolate(value)
    return "#000000"
