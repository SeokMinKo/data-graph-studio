"""
Tests for Annotation feature — PRD Section 3.5 (Feature 5)

UT-5.1: Annotation 생성/직렬화/역직렬화
UT-5.2: Annotation 좌표 변환 (줌/팬 시)
UT-5.3: Annotation 편집/삭제
UT-5.4: Annotation 텍스트 200자 초과 → 차단
UT-5.5: Orphaned annotation 감지 (데이터셋 삭제 후)
"""

import json
import uuid
import pytest

from data_graph_studio.core.annotation import Annotation


# ── Helper ──────────────────────────────────────────────────────


def make_annotation(**overrides) -> Annotation:
    defaults = dict(
        id=str(uuid.uuid4())[:8],
        kind="point",
        x=10.0,
        x_end=0.0,
        y=20.0,
        text="Peak voltage",
        color="#FF0000",
        icon="⚠️",
        dataset_id="ds-1",
        profile_id="prof-1",
    )
    defaults.update(overrides)
    return Annotation(**defaults)


def make_range_annotation(**overrides) -> Annotation:
    defaults = dict(
        id=str(uuid.uuid4())[:8],
        kind="range",
        x=5.0,
        x_end=15.0,
        y=None,
        text="Noise region",
        color="#0000FF",
        icon="🔵",
        dataset_id="ds-1",
        profile_id="prof-1",
    )
    defaults.update(overrides)
    return Annotation(**defaults)


# ── UT-5.1: Annotation 생성/직렬화/역직렬화 ─────────────────────


class TestAnnotationSerialization:
    """UT-5.1: Annotation 생성/직렬화/역직렬화"""

    def test_point_annotation_creation(self):
        ann = make_annotation()
        assert ann.kind == "point"
        assert ann.x == 10.0
        assert ann.y == 20.0
        assert ann.text == "Peak voltage"
        assert ann.color == "#FF0000"
        assert ann.icon == "⚠️"
        assert ann.dataset_id == "ds-1"
        assert ann.profile_id == "prof-1"

    def test_range_annotation_creation(self):
        ann = make_range_annotation()
        assert ann.kind == "range"
        assert ann.x == 5.0
        assert ann.x_end == 15.0
        assert ann.y is None

    def test_to_dict(self):
        ann = make_annotation(id="ann-1")
        d = ann.to_dict()
        assert d["id"] == "ann-1"
        assert d["kind"] == "point"
        assert d["x"] == 10.0
        assert d["y"] == 20.0
        assert d["color"] == "#FF0000"
        assert d["icon"] == "⚠️"
        assert d["dataset_id"] == "ds-1"
        assert d["profile_id"] == "prof-1"
        # is_orphaned는 런타임 상태이므로 직렬화 제외
        assert "is_orphaned" not in d
        # sparse: x_end=0.0은 기본값이므로 포함되지 않음
        assert "x_end" not in d

    def test_to_dict_range(self):
        ann = make_range_annotation(id="rng-1")
        d = ann.to_dict()
        assert d["x_end"] == 15.0
        # y=None은 포함되지 않음
        assert "y" not in d

    def test_from_dict(self):
        data = {
            "id": "ann-2",
            "kind": "range",
            "x": 5.0,
            "x_end": 15.0,
            "text": "Noise region",
            "color": "#0000FF",
            "icon": "🔵",
            "dataset_id": "ds-1",
            "profile_id": "prof-1",
        }
        ann = Annotation.from_dict(data)
        assert ann.id == "ann-2"
        assert ann.kind == "range"
        assert ann.x == 5.0
        assert ann.x_end == 15.0
        assert ann.y is None  # missing → default None

    def test_round_trip_serialization(self):
        original = make_annotation(id="ann-rt")
        d = original.to_dict()
        restored = Annotation.from_dict(d)
        assert restored.id == original.id
        assert restored.kind == original.kind
        assert restored.x == original.x
        assert restored.y == original.y
        assert restored.text == original.text
        assert restored.color == original.color
        assert restored.icon == original.icon

    def test_json_serialization(self):
        ann = make_annotation(id="ann-json")
        json_str = json.dumps(ann.to_dict())
        restored = Annotation.from_dict(json.loads(json_str))
        assert restored.id == "ann-json"
        assert restored.text == "Peak voltage"

    def test_annotation_data_within_size_limit(self):
        """NFR-5.2: 주석 데이터 < 100KB (1000개 기준, 프로파일 저장 시 컴팩트 형식)"""
        annotations = [
            make_annotation(id=f"a{i}", text=f"Note {i}", icon="📌")
            for i in range(1000)
        ]
        # 프로파일 저장 시 컴팩트 형식 사용
        data = json.dumps(
            [a.to_compact_dict() for a in annotations],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        assert len(data.encode("utf-8")) < 100 * 1024  # < 100KB

    def test_compact_round_trip(self):
        """컴팩트 직렬화 ↔ 역직렬화"""
        ann = make_annotation(id="cmp-1", text="Test", color="#00FF00", icon="⭐")
        compact = ann.to_compact_dict()
        restored = Annotation.from_compact_dict(compact, profile_id="prof-1")
        assert restored.id == "cmp-1"
        assert restored.text == "Test"
        assert restored.color == "#00FF00"
        assert restored.icon == "⭐"
        assert restored.profile_id == "prof-1"


# ── UT-5.2: Annotation 좌표 변환 ────────────────────────────────


class TestAnnotationCoordinateTransform:
    """UT-5.2: Annotation 좌표 변환 (줌/팬 시)"""

    def test_point_annotation_data_coordinates_preserved(self):
        """주석은 데이터 좌표에 앵커됨 — 좌표 자체는 변하지 않는다"""
        ann = make_annotation(x=100.0, y=50.0)
        # 데이터 좌표는 줌/팬과 무관하게 항상 동일
        assert ann.x == 100.0
        assert ann.y == 50.0

    def test_transform_to_screen_coords(self):
        """데이터 좌표 → 화면 좌표 변환 (줌/팬 적용)"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(x=100.0, y=50.0)
        ctrl.add(ann)

        # 뷰 범위: x=[0, 200], y=[0, 100], 화면 크기: 800x600
        view_rect = {"x_min": 0, "x_max": 200, "y_min": 0, "y_max": 100}
        screen_size = {"width": 800, "height": 600}

        sx, sy = ctrl.data_to_screen(ann.x, ann.y, view_rect, screen_size)
        assert sx == pytest.approx(400.0)  # 100/200 * 800
        assert sy == pytest.approx(300.0)  # 50/100 * 600

    def test_transform_after_zoom(self):
        """줌 후 화면 좌표 변경"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(x=100.0, y=50.0)
        ctrl.add(ann)

        # 줌 인: x=[50, 150], y=[25, 75]
        view_rect = {"x_min": 50, "x_max": 150, "y_min": 25, "y_max": 75}
        screen_size = {"width": 800, "height": 600}

        sx, sy = ctrl.data_to_screen(ann.x, ann.y, view_rect, screen_size)
        assert sx == pytest.approx(400.0)  # (100-50)/(150-50) * 800
        assert sy == pytest.approx(300.0)  # (50-25)/(75-25) * 600

    def test_transform_after_pan(self):
        """팬 후 화면 좌표 변경"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(x=100.0, y=50.0)
        ctrl.add(ann)

        # 팬: x=[100, 300], y=[50, 150]
        view_rect = {"x_min": 100, "x_max": 300, "y_min": 50, "y_max": 150}
        screen_size = {"width": 800, "height": 600}

        sx, sy = ctrl.data_to_screen(ann.x, ann.y, view_rect, screen_size)
        assert sx == pytest.approx(0.0)    # (100-100)/(300-100) * 800
        assert sy == pytest.approx(0.0)    # (50-50)/(150-50) * 600

    def test_range_annotation_screen_coords(self):
        """구간 주석의 화면 좌표 변환"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_range_annotation(x=50.0, x_end=150.0)
        ctrl.add(ann)

        view_rect = {"x_min": 0, "x_max": 200, "y_min": 0, "y_max": 100}
        screen_size = {"width": 800, "height": 600}

        sx_start, _ = ctrl.data_to_screen(ann.x, 0, view_rect, screen_size)
        sx_end, _ = ctrl.data_to_screen(ann.x_end, 0, view_rect, screen_size)

        assert sx_start == pytest.approx(200.0)  # 50/200 * 800
        assert sx_end == pytest.approx(600.0)     # 150/200 * 800


# ── UT-5.3: Annotation 편집/삭제 ────────────────────────────────


class TestAnnotationEditDelete:
    """UT-5.3: Annotation 편집/삭제"""

    def test_add_annotation(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(id="add-1")
        ctrl.add(ann)

        result = ctrl.get("add-1")
        assert result is not None
        assert result.text == "Peak voltage"

    def test_edit_annotation_text(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(id="edit-1")
        ctrl.add(ann)

        ctrl.edit("edit-1", text="Updated text")
        result = ctrl.get("edit-1")
        assert result.text == "Updated text"

    def test_edit_annotation_color(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(id="edit-color")
        ctrl.add(ann)

        ctrl.edit("edit-color", color="#00FF00")
        result = ctrl.get("edit-color")
        assert result.color == "#00FF00"

    def test_edit_annotation_icon(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(id="edit-icon")
        ctrl.add(ann)

        ctrl.edit("edit-icon", icon="⭐")
        result = ctrl.get("edit-icon")
        assert result.icon == "⭐"

    def test_delete_annotation(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ann = make_annotation(id="del-1")
        ctrl.add(ann)

        assert ctrl.delete("del-1") is True
        assert ctrl.get("del-1") is None

    def test_delete_nonexistent_annotation(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        assert ctrl.delete("nonexistent") is False

    def test_list_annotations_by_profile(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", profile_id="prof-1"))
        ctrl.add(make_annotation(id="a2", profile_id="prof-1"))
        ctrl.add(make_annotation(id="a3", profile_id="prof-2"))

        result = ctrl.list_by_profile("prof-1")
        assert len(result) == 2
        assert {a.id for a in result} == {"a1", "a2"}

    def test_list_annotations_by_dataset(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1"))
        ctrl.add(make_annotation(id="a2", dataset_id="ds-2"))
        ctrl.add(make_annotation(id="a3", dataset_id="ds-1"))

        result = ctrl.list_by_dataset("ds-1")
        assert len(result) == 2

    def test_list_all_annotations(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1"))
        ctrl.add(make_annotation(id="a2"))

        result = ctrl.list_all()
        assert len(result) == 2

    def test_edit_nonexistent_returns_false(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        assert ctrl.edit("nonexistent", text="test") is False


# ── UT-5.4: Annotation 텍스트 200자 초과 → 차단 ─────────────────


class TestAnnotationTextLimit:
    """UT-5.4: Annotation 텍스트 200자 초과 → 차단 (ERR-5.1)"""

    def test_text_exactly_200_chars(self):
        """200자 정확히 → 허용"""
        text = "A" * 200
        ann = make_annotation(text=text)
        assert len(ann.text) == 200

    def test_text_201_chars_raises(self):
        """201자 → ValidationError 발생"""
        from data_graph_studio.core.exceptions import ValidationError
        text = "A" * 201
        with pytest.raises(ValidationError, match="200"):
            make_annotation(text=text)

    def test_add_annotation_with_long_text_raises(self):
        """컨트롤러에서 200자 초과 주석 추가 시 차단"""
        from data_graph_studio.core.annotation_controller import AnnotationController
        from data_graph_studio.core.exceptions import ValidationError

        ctrl = AnnotationController()
        text = "B" * 201
        with pytest.raises(ValidationError, match="200"):
            ctrl.add(make_annotation(text=text))

    def test_edit_annotation_with_long_text_raises(self):
        """컨트롤러에서 200자 초과 편집 시 차단"""
        from data_graph_studio.core.annotation_controller import AnnotationController
        from data_graph_studio.core.exceptions import ValidationError

        ctrl = AnnotationController()
        ann = make_annotation(id="limit-edit", text="short")
        ctrl.add(ann)

        with pytest.raises(ValidationError, match="200"):
            ctrl.edit("limit-edit", text="C" * 201)

    def test_empty_text_allowed(self):
        """빈 텍스트 허용"""
        ann = make_annotation(text="")
        assert ann.text == ""


# ── UT-5.5: Orphaned annotation 감지 ────────────────────────────


class TestOrphanedAnnotation:
    """UT-5.5: Orphaned annotation 감지 (데이터셋 삭제 후, ERR-5.3)"""

    def test_detect_orphaned_annotations(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1"))
        ctrl.add(make_annotation(id="a2", dataset_id="ds-2"))
        ctrl.add(make_annotation(id="a3", dataset_id="ds-1"))

        # 활성 데이터셋: ds-2만 남음
        active_dataset_ids = {"ds-2"}
        orphaned = ctrl.find_orphaned(active_dataset_ids)

        assert len(orphaned) == 2
        assert {a.id for a in orphaned} == {"a1", "a3"}

    def test_no_orphans_when_all_datasets_active(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1"))
        ctrl.add(make_annotation(id="a2", dataset_id="ds-2"))

        active_dataset_ids = {"ds-1", "ds-2"}
        orphaned = ctrl.find_orphaned(active_dataset_ids)

        assert len(orphaned) == 0

    def test_all_orphaned_when_no_datasets(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1"))
        ctrl.add(make_annotation(id="a2", dataset_id="ds-2"))

        orphaned = ctrl.find_orphaned(set())
        assert len(orphaned) == 2

    def test_mark_orphaned(self):
        """Orphaned 주석을 회색으로 표시"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1", color="#FF0000"))

        ctrl.mark_orphaned({"ds-2"})  # ds-1은 활성 목록에 없음

        ann = ctrl.get("a1")
        assert ann.is_orphaned is True

    def test_unmark_orphaned_when_dataset_restored(self):
        """데이터셋 복원 시 orphaned 해제"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1"))

        ctrl.mark_orphaned({"ds-2"})  # orphaned
        assert ctrl.get("a1").is_orphaned is True

        ctrl.mark_orphaned({"ds-1", "ds-2"})  # 복원
        assert ctrl.get("a1").is_orphaned is False

    def test_bulk_delete_orphaned(self):
        """Orphaned 주석 일괄 삭제"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", dataset_id="ds-1"))
        ctrl.add(make_annotation(id="a2", dataset_id="ds-2"))
        ctrl.add(make_annotation(id="a3", dataset_id="ds-1"))

        ctrl.mark_orphaned({"ds-2"})
        deleted = ctrl.delete_orphaned()

        assert deleted == 2
        assert ctrl.get("a1") is None
        assert ctrl.get("a3") is None
        assert ctrl.get("a2") is not None


# ── Profile integration ─────────────────────────────────────────


class TestAnnotationProfileIntegration:
    """주석-프로파일 연동 테스트"""

    def test_export_annotations_for_profile(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", profile_id="prof-1"))
        ctrl.add(make_annotation(id="a2", profile_id="prof-1"))
        ctrl.add(make_annotation(id="a3", profile_id="prof-2"))

        exported = ctrl.export_for_profile("prof-1")
        assert len(exported) == 2
        assert all(isinstance(d, dict) for d in exported)

    def test_import_annotations_for_profile(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        data = [
            make_annotation(id="imp-1", profile_id="prof-1").to_dict(),
            make_annotation(id="imp-2", profile_id="prof-1").to_dict(),
        ]

        ctrl.import_for_profile("prof-1", data)
        result = ctrl.list_by_profile("prof-1")
        assert len(result) == 2

    def test_import_replaces_existing(self):
        """같은 프로파일로 import 시 기존 주석 교체"""
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="old-1", profile_id="prof-1"))

        new_data = [
            make_annotation(id="new-1", profile_id="prof-1").to_dict(),
        ]
        ctrl.import_for_profile("prof-1", new_data)

        result = ctrl.list_by_profile("prof-1")
        assert len(result) == 1
        assert result[0].id == "new-1"

    def test_clear_annotations_for_profile(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController()
        ctrl.add(make_annotation(id="a1", profile_id="prof-1"))
        ctrl.add(make_annotation(id="a2", profile_id="prof-2"))

        ctrl.clear_profile("prof-1")

        assert len(ctrl.list_by_profile("prof-1")) == 0
        assert len(ctrl.list_by_profile("prof-2")) == 1


# ── Undo integration (optional) ────────────────────────────────


class TestAnnotationUndoIntegration:
    """주석 Undo 연동 — UndoManager가 없어도 동작해야 함"""

    def test_controller_works_without_undo_manager(self):
        from data_graph_studio.core.annotation_controller import AnnotationController

        ctrl = AnnotationController(undo_manager=None)
        ann = make_annotation(id="no-undo")
        ctrl.add(ann)
        assert ctrl.get("no-undo") is not None
        ctrl.delete("no-undo")
        assert ctrl.get("no-undo") is None
