"""
Tests for Graph Profiles functionality
"""

import pytest
import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from data_graph_studio.core.profile import GraphSetting, Profile, ProfileManager
from data_graph_studio.core.state import AppState, ChartType, AggregationType
from data_graph_studio.ui.adapters.app_state_adapter import AppStateAdapter


class TestGraphSetting:
    """GraphSetting 클래스 테스트"""

    def test_create_new(self):
        """새 설정 생성 테스트"""
        setting = GraphSetting.create_new("Test Setting", "📈")

        assert setting.name == "Test Setting"
        assert setting.icon == "📈"
        assert setting.id is not None
        assert len(setting.id) > 0
        assert setting.created_at > 0
        assert setting.modified_at > 0

    def test_to_dict(self):
        """딕셔너리 변환 테스트"""
        import dataclasses
        setting = GraphSetting.create_new("Test", "📊")
        setting = dataclasses.replace(
            setting,
            chart_type="bar",
            x_column="date",
            value_columns=({"name": "sales", "aggregation": "sum"},),
        )

        data = setting.to_dict()

        assert data["name"] == "Test"
        assert data["icon"] == "📊"
        assert data["chart_type"] == "bar"
        assert data["x_column"] == "date"
        assert len(data["value_columns"]) == 1

    def test_from_dict(self):
        """딕셔너리에서 복원 테스트"""
        data = {
            "id": "test-id-123",
            "name": "Restored Setting",
            "icon": "📉",
            "chart_type": "scatter",
            "x_column": "time",
            "group_columns": [{"name": "category"}],
            "value_columns": [{"name": "value", "aggregation": "mean"}],
        }

        setting = GraphSetting.from_dict(data)

        assert setting.id == "test-id-123"
        assert setting.name == "Restored Setting"
        assert setting.icon == "📉"
        assert setting.chart_type == "scatter"
        assert setting.x_column == "time"
        assert len(setting.group_columns) == 1
        assert len(setting.value_columns) == 1

    def test_update_modified(self):
        """수정 시간 업데이트 테스트"""
        setting = GraphSetting.create_new("Test")
        original_time = setting.modified_at

        time.sleep(0.02)  # 시간 차이를 위한 대기
        updated = setting.update_modified()

        assert updated.modified_at > original_time


class TestProfile:
    """Profile 클래스 테스트"""

    def test_create_new(self):
        """새 프로파일 생성 테스트"""
        profile = Profile.create_new("Test Profile")

        assert profile.name == "Test Profile"
        assert profile.id is not None
        assert len(profile.settings) == 0

    def test_add_setting(self):
        """설정 추가 테스트"""
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Setting 1")

        profile.add_setting(setting)

        assert len(profile.settings) == 1
        assert profile.settings[0].name == "Setting 1"

    def test_remove_setting(self):
        """설정 제거 테스트"""
        profile = Profile.create_new("Test")
        setting1 = GraphSetting.create_new("Setting 1")
        setting2 = GraphSetting.create_new("Setting 2")

        profile.add_setting(setting1)
        profile.add_setting(setting2)
        assert len(profile.settings) == 2

        result = profile.remove_setting(setting1.id)

        assert result is True
        assert len(profile.settings) == 1
        assert profile.settings[0].name == "Setting 2"

    def test_remove_nonexistent_setting(self):
        """존재하지 않는 설정 제거 테스트"""
        profile = Profile.create_new("Test")

        result = profile.remove_setting("nonexistent-id")

        assert result is False

    def test_get_setting(self):
        """설정 가져오기 테스트"""
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Test Setting")
        profile.add_setting(setting)

        result = profile.get_setting(setting.id)

        assert result is not None
        assert result.name == "Test Setting"

    def test_get_setting_by_name(self):
        """이름으로 설정 가져오기 테스트"""
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Unique Name")
        profile.add_setting(setting)

        result = profile.get_setting_by_name("Unique Name")

        assert result is not None
        assert result.id == setting.id

    def test_reorder_settings(self):
        """설정 순서 변경 테스트"""
        profile = Profile.create_new("Test")
        s1 = GraphSetting.create_new("Setting 1")
        s2 = GraphSetting.create_new("Setting 2")
        s3 = GraphSetting.create_new("Setting 3")

        profile.add_setting(s1)
        profile.add_setting(s2)
        profile.add_setting(s3)

        # 순서 변경: 3, 1, 2
        profile.reorder_settings([s3.id, s1.id, s2.id])

        assert profile.settings[0].name == "Setting 3"
        assert profile.settings[1].name == "Setting 1"
        assert profile.settings[2].name == "Setting 2"

    def test_to_json_and_from_json(self):
        """JSON 직렬화/역직렬화 테스트"""
        import dataclasses
        profile = Profile.create_new("JSON Test")
        profile.description = "Test description"
        setting = GraphSetting.create_new("Test Setting", "📈")
        setting = dataclasses.replace(setting, chart_type="line", x_column="date")
        profile.add_setting(setting)
        profile.default_setting_id = setting.id

        json_str = profile.to_json()
        restored = Profile.from_json(json_str)

        assert restored.name == "JSON Test"
        assert restored.description == "Test description"
        assert len(restored.settings) == 1
        assert restored.settings[0].chart_type == "line"
        assert restored.default_setting_id == setting.id

    def test_save_and_load(self, tmp_path):
        """파일 저장/로드 테스트"""
        profile = Profile.create_new("File Test")
        setting = GraphSetting.create_new("Setting")
        profile.add_setting(setting)

        file_path = str(tmp_path / "test.dgp")
        profile.save(file_path)

        loaded = Profile.load(file_path)

        assert loaded.name == "File Test"
        assert len(loaded.settings) == 1
        assert loaded._path == file_path

    def test_check_compatibility(self):
        """호환성 검사 테스트"""
        import dataclasses
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Setting")
        setting = dataclasses.replace(setting, x_column="date")
        setting = dataclasses.replace(
            setting,
            group_columns=({"name": "category"},),
            value_columns=({"name": "sales"}, {"name": "profit"}),
        )
        profile.add_setting(setting)

        # 일부 컬럼만 있는 데이터
        result = profile.check_compatibility(["date", "category", "sales"])

        assert "date" in result["available"]
        assert "category" in result["available"]
        assert "sales" in result["available"]
        assert "profit" in result["missing"]


class TestProfileManager:
    """ProfileManager 클래스 테스트"""

    def test_new_profile(self):
        """새 프로파일 생성 테스트"""
        manager = ProfileManager()

        profile = manager.new_profile("New Profile")

        assert profile is not None
        assert profile.name == "New Profile"
        assert manager.current_profile == profile
        assert manager.is_dirty is False

    def test_mark_dirty(self):
        """수정 표시 테스트"""
        manager = ProfileManager()
        manager.new_profile("Test")

        manager.mark_dirty()

        assert manager.is_dirty is True

    def test_save_and_load(self, tmp_path):
        """저장/로드 테스트"""
        manager = ProfileManager()
        manager._profiles_dir = tmp_path  # 테스트용 디렉토리

        profile = manager.new_profile("Save Test")
        setting = GraphSetting.create_new("Setting")
        profile.add_setting(setting)

        save_path = str(tmp_path / "test.dgp")
        manager.save(save_path)

        # 새 매니저로 로드
        manager2 = ProfileManager()
        loaded = manager2.load(save_path)

        assert loaded.name == "Save Test"
        assert len(loaded.settings) == 1

    def test_recent_profiles(self, tmp_path):
        """최근 프로파일 관리 테스트"""
        manager = ProfileManager()
        manager._profiles_dir = tmp_path
        manager._recent_profiles = []  # Clear any existing recent profiles

        # 여러 프로파일 저장
        for i in range(3):
            profile = manager.new_profile(f"Profile {i}")
            manager.save(str(tmp_path / f"profile_{i}.dgp"))

        recent = manager.get_recent_profiles()

        assert len(recent) == 3
        # 가장 최근 것이 첫 번째
        assert "profile_2.dgp" in recent[0]

    def test_add_setting_to_current(self):
        """현재 프로파일에 설정 추가 테스트"""
        manager = ProfileManager()
        manager.new_profile("Test")

        setting = GraphSetting.create_new("New Setting")
        manager.add_setting_to_current(setting)

        assert len(manager.current_profile.settings) == 1
        assert manager.is_dirty is True

    def test_remove_setting_from_current(self):
        """현재 프로파일에서 설정 제거 테스트"""
        manager = ProfileManager()
        manager.new_profile("Test")
        setting = GraphSetting.create_new("Setting")
        manager.add_setting_to_current(setting)

        result = manager.remove_setting_from_current(setting.id)

        assert result is True
        assert len(manager.current_profile.settings) == 0


class TestAppStateProfile:
    """AppState의 Profile 관련 기능 테스트"""

    def test_set_profile(self):
        """프로파일 설정 테스트"""
        state = AppState()
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Setting")
        profile.add_setting(setting)
        profile.default_setting_id = setting.id

        state.set_profile(profile)

        assert state.current_profile == profile
        assert state.current_setting_id == setting.id

    def test_activate_setting(self):
        """설정 활성화 테스트"""
        state = AppState()
        profile = Profile.create_new("Test")
        s1 = GraphSetting.create_new("Setting 1")
        s2 = GraphSetting.create_new("Setting 2")
        profile.add_setting(s1)
        profile.add_setting(s2)
        state.set_profile(profile)

        state.activate_setting(s2.id)

        assert state.current_setting_id == s2.id

    def test_add_and_remove_setting(self):
        """설정 추가/제거 테스트"""
        state = AppState()
        profile = Profile.create_new("Test")
        state.set_profile(profile)

        setting = GraphSetting.create_new("New Setting")
        state.add_setting(setting)

        assert len(state.current_profile.settings) == 1

        state.remove_setting(setting.id)

        assert len(state.current_profile.settings) == 0

    def test_get_current_graph_state(self):
        """현재 그래프 상태 가져오기 테스트"""
        state = AppState()
        state.set_chart_type(ChartType.BAR)
        state.set_x_column("date")
        state.add_value_column("sales", AggregationType.SUM)

        graph_state = state.get_current_graph_state()

        assert graph_state["chart_type"] == "bar"
        assert graph_state["x_column"] == "date"
        assert len(graph_state["value_columns"]) == 1
        assert graph_state["value_columns"][0]["name"] == "sales"

    def test_apply_graph_setting(self):
        """GraphSetting 적용 테스트"""
        import dataclasses
        state = AppState()

        setting = GraphSetting.create_new("Test")
        setting = dataclasses.replace(
            setting,
            chart_type="scatter",
            x_column="time",
            group_columns=({"name": "category", "selected_values": [], "order": 0},),
            value_columns=(
                {"name": "value", "aggregation": "mean", "color": "#ff0000", "use_secondary_axis": False, "order": 0, "formula": ""},
            ),
            chart_settings={"line_width": 3, "marker_size": 8},
        )

        state.apply_graph_setting(setting)

        assert state.chart_settings.chart_type == ChartType.SCATTER
        assert state.x_column == "time"
        assert len(state.group_columns) == 1
        assert state.group_columns[0].name == "category"
        assert len(state.value_columns) == 1
        assert state.value_columns[0].name == "value"
        assert state.value_columns[0].aggregation == AggregationType.MEAN

    def test_floating_window_management(self):
        """플로팅 윈도우 관리 테스트"""
        state = AppState()
        mock_window = MagicMock()

        state.register_floating_window("window-1", mock_window)

        assert "window-1" in state.floating_windows
        assert state.floating_windows["window-1"] == mock_window

        state.unregister_floating_window("window-1")

        assert "window-1" not in state.floating_windows


@pytest.mark.skipif(
    not hasattr(pytest, 'importorskip'),
    reason="Signal tests require full Qt environment"
)
class TestProfileSignals:
    """Profile 관련 Signal 테스트"""

    @pytest.fixture(autouse=True)
    def setup_qapp(self, qtbot):
        """Ensure QApplication exists"""
        pass

    def test_profile_loaded_signal(self, qtbot):
        """profile_loaded 시그널 테스트"""
        state = AppState()
        adapter = AppStateAdapter(state)
        profile = Profile.create_new("Test")

        with qtbot.waitSignal(adapter.profile_loaded, timeout=1000):
            state.set_profile(profile)

    def test_profile_cleared_signal(self, qtbot):
        """profile_cleared 시그널 테스트"""
        state = AppState()
        adapter = AppStateAdapter(state)
        profile = Profile.create_new("Test")
        state.set_profile(profile)

        with qtbot.waitSignal(adapter.profile_cleared, timeout=1000):
            state.set_profile(None)

    def test_setting_activated_signal(self, qtbot):
        """setting_activated 시그널 테스트"""
        state = AppState()
        adapter = AppStateAdapter(state)
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Setting")
        profile.add_setting(setting)
        state.set_profile(profile)

        with qtbot.waitSignal(adapter.setting_activated, timeout=1000):
            state.activate_setting(setting.id)

    def test_setting_added_signal(self, qtbot):
        """setting_added 시그널 테스트"""
        state = AppState()
        adapter = AppStateAdapter(state)
        profile = Profile.create_new("Test")
        state.set_profile(profile)

        setting = GraphSetting.create_new("New")

        with qtbot.waitSignal(adapter.setting_added, timeout=1000):
            state.add_setting(setting)

    def test_setting_removed_signal(self, qtbot):
        """setting_removed 시그널 테스트"""
        state = AppState()
        adapter = AppStateAdapter(state)
        profile = Profile.create_new("Test")
        setting = GraphSetting.create_new("Setting")
        profile.add_setting(setting)
        state.set_profile(profile)

        with qtbot.waitSignal(adapter.setting_removed, timeout=1000):
            state.remove_setting(setting.id)
