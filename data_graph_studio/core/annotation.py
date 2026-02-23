"""
Annotation — 데이터 주석/북마크 데이터 구조

PRD Section 6.4, Feature 5 (3.5.x)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Dict, Any

from data_graph_studio.core.constants import MAX_ANNOTATION_TEXT_LENGTH
from data_graph_studio.core.exceptions import ValidationError


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
        """Validate the annotation after dataclass initialization.

        Output: None
        Raises: ValidationError — when text exceeds MAX_ANNOTATION_TEXT_LENGTH characters
        """
        if len(self.text) > MAX_ANNOTATION_TEXT_LENGTH:
            raise ValidationError(
                f"Annotation text exceeds {MAX_ANNOTATION_TEXT_LENGTH} characters "
                f"(got {len(self.text)})",
                operation="Annotation.__post_init__",
                context={"text_length": len(self.text), "max_length": MAX_ANNOTATION_TEXT_LENGTH},
            )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize the annotation to a dict, excluding runtime-only is_orphaned field.

        Output: Dict[str, Any] — JSON-serializable dict with id, kind, x, text, color,
                                  icon, dataset_id, profile_id; x_end and y only when non-default
        """
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
        """Compact serialization for profile storage, omitting profile_id and default values.

        Output: Dict[str, Any] — sparse dict using abbreviated keys (k, x, t, xe, y, c, i, ds);
                                  fields equal to their defaults are omitted to reduce payload size
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
        """Restore an Annotation from a compact dict produced by to_compact_dict.

        Input: data — Dict[str, Any], compact dict with abbreviated keys
               profile_id — str, profile to assign (overrides any stored value, default "")
               dataset_id — str, dataset to assign when not present in data (default "")
        Output: Annotation — reconstructed instance with defaults applied for missing keys
        Raises: ValidationError — when the restored text exceeds MAX_ANNOTATION_TEXT_LENGTH
        """
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
        """Restore an Annotation from a full dict produced by to_dict.

        Input: data — Dict[str, Any], dict with full-length keys (id, kind, x, text, color, etc.)
        Output: Annotation — reconstructed instance with defaults applied for missing optional keys
        Raises: ValidationError — when the restored text exceeds MAX_ANNOTATION_TEXT_LENGTH
        """
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
