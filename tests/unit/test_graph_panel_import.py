"""Backward compatibility test: GraphPanel must remain importable from original path."""


def test_graph_panel_importable_from_original_path():
    """Backward compat: original import path must still work."""
    from data_graph_studio.ui.panels.graph_panel import GraphPanel
    assert GraphPanel is not None


def test_graph_panel_is_class():
    """GraphPanel must be a class, not a module or other object."""
    from data_graph_studio.ui.panels.graph_panel import GraphPanel
    import inspect
    assert inspect.isclass(GraphPanel)


def test_graph_panel_importable_from_panels_init():
    """GraphPanel must also be importable from the panels package __init__."""
    from data_graph_studio.ui.panels import GraphPanel
    assert GraphPanel is not None
