import dataclasses
from dataclasses import dataclass

from PySide6.QtCore import Qt, QModelIndex

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.core.state import AppState
from data_graph_studio.ui.models.profile_model import ProfileModel


@dataclass
class FakeProfileStore:
    profiles_by_dataset: dict

    def get_profiles(self, dataset_id: str):
        return self.profiles_by_dataset.get(dataset_id, [])


def _build_model():
    state = AppState()
    state.add_dataset("ds1", name="Project Alpha")
    state.add_dataset("ds2", name="Project Beta")

    setting_one = GraphSetting.create_new("Sales")
    setting_one = dataclasses.replace(setting_one, icon="📈", chart_type="line")

    setting_two = GraphSetting.create_new("Revenue")
    setting_two = dataclasses.replace(setting_two, icon="📊", chart_type="bar")

    store = FakeProfileStore(
        {
            "ds1": [setting_one, setting_two],
            "ds2": [],
        }
    )

    model = ProfileModel(store, state)
    return model, setting_one, setting_two


def test_row_count_projects():
    model, _, _ = _build_model()

    assert model.rowCount(QModelIndex()) == 2


def test_row_count_profiles():
    model, _, _ = _build_model()

    project_index = model.index(0, 0, QModelIndex())
    empty_project_index = model.index(1, 0, QModelIndex())

    assert model.rowCount(project_index) == 2
    assert model.rowCount(empty_project_index) == 0


def test_data_display_role():
    model, setting_one, _ = _build_model()

    project_index = model.index(0, 0, QModelIndex())
    setting_index = model.index(0, 0, project_index)

    assert model.data(project_index, Qt.DisplayRole) == "Project Alpha"
    assert model.data(setting_index, Qt.DisplayRole) == setting_one.name


def test_get_setting():
    model, setting_one, _ = _build_model()

    project_index = model.index(0, 0, QModelIndex())
    setting_index = model.index(0, 0, project_index)

    assert model.get_setting(project_index) is None
    assert model.get_setting(setting_index) is setting_one


def test_parent_child_relationship():
    model, _, _ = _build_model()

    project_index = model.index(0, 0, QModelIndex())
    setting_index = model.index(0, 0, project_index)

    parent_index = model.parent(setting_index)

    assert parent_index.isValid()
    assert parent_index.row() == project_index.row()
    assert parent_index.parent().isValid() is False
    assert model.parent(project_index).isValid() is False
