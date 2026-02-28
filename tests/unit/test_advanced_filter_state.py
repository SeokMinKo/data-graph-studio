from data_graph_studio.core.state import AppState
from data_graph_studio.core.filter_ast import PredicateNode, node_to_dict


def test_app_state_advanced_filter_preset_roundtrip():
    state = AppState()
    ast = PredicateNode("col", "eq", 1)

    state.set_advanced_filter_ast(ast)
    state.save_filter_preset("p1", ast)

    loaded = state.load_filter_preset("p1")

    assert node_to_dict(loaded) == node_to_dict(ast)
    assert "p1" in state.filter_presets
