"""
Annotation — 데이터 주석/북마크 데이터 구조

PRD Section 6.4, Feature 5 (3.5.x)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any


MAX_ANNOTATION_TEXT_LENGTH = 200


@dataclass
class Annotation:
    """
    데이터 주석/북마크.

    kind:
        "point" — 단일 데이터 포인트 주석 (x, y 좌표)
        "range" — X축 구간 북마크 (x ~ x_end)

    Attributes:
        id: 고유 식별자
        kind: "point" | "range"
        x: X 좌표 (point) 또는 x_start (range)
        x_end: range 전용 — 구간 끝 X 좌표
        y: point 전용 — Y 좌표
        text: 주석 텍스트 (최대 200자, ERR-5.1)
        color: 색상 (hex)
        icon: 아이콘 (emoji)
        dataset_id: 소속 데이터셋 ID
        profile_id: 소속 프로파일 ID
        is_orphaned: 데이터셋 삭제 시 orphaned 상태 (ERR-5.3)
    """

    id: str
    kind: str  # "point" | "range"
    x: float
    x_end: float = 0.0
    y: Optional[float] = None
    text: str = ""
    color: str = "#FF0000"
    icon: str = "📌"
    dataset_id: str = ""
    profile_id: str = ""
    is_orphaned: bool = False

    def __post_init__(self):
        if len(self.text) > MAX_ANNOTATION_TEXT_LENGTH:
            raise ValueError(
                f"Annotation text exceeds {MAX_ANNOTATION_TEXT_LENGTH} characters "
                f"(got {len(self.text)})"
            )

    def to_dict(self) -> Dict[str, Any]:
        """직렬화 → dict (is_orphaned는 런타임 상태이므로 제외)"""
        d: Dict[str, Any] = {
            "id": self.id,
            "kind": self.kind,
            "x": self.x,
            "text": self.text,
            "color": self.color,
            "icon": self.icon,
            "dataset_id": self.dataset_id,
            "profile_id": self.profile_id,
        }
        # Sparse serialization — 기본값이 아닌 필드만 포함
        if self.x_end != 0.0:
            d["x_end"] = self.x_end
        if self.y is not None:
            d["y"] = self.y
        return d

    def to_compact_dict(self) -> Dict[str, Any]:
        """
        프로파일 저장용 컴팩트 직렬화.
        profile_id와 dataset_id는 상위 컨텍스트에서 제공하므로 제외.
        """
        d: Dict[str, Any] = {
            "id": self.id,
            "k": self.kind[0],  # "p" or "r"
            "x": self.x,
            "t": self.text,
        }
        if self.x_end != 0.0:
            d["xe"] = self.x_end
        if self.y is not None:
            d["y"] = self.y
        if self.color != "#FF0000":
            d["c"] = self.color
        if self.icon != "📌":
            d["i"] = self.icon
        if self.dataset_id:
            d["ds"] = self.dataset_id
        return d

    @classmethod
    def from_compact_dict(
        cls, data: Dict[str, Any], profile_id: str = "", dataset_id: str = ""
    ) -> Annotation:
        """컴팩트 dict에서 복원."""
        kind_map = {"p": "point", "r": "range"}
        return cls(
            id=data["id"],
            kind=kind_map.get(data.get("k", "p"), "point"),
            x=data["x"],
            x_end=data.get("xe", 0.0),
            y=data.get("y"),
            text=data.get("t", ""),
            color=data.get("c", "#FF0000"),
            icon=data.get("i", "📌"),
            dataset_id=data.get("ds", dataset_id),
            profile_id=profile_id,
        )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Annotation:
        """dict → 역직렬화"""
        return cls(
            id=data["id"],
            kind=data["kind"],
            x=data["x"],
            x_end=data.get("x_end", 0.0),
            y=data.get("y"),
            text=data.get("text", ""),
            color=data.get("color", "#FF0000"),
            icon=data.get("icon", "📌"),
            dataset_id=data.get("dataset_id", ""),
            profile_id=data.get("profile_id", ""),
            is_orphaned=data.get("is_orphaned", False),
        )
