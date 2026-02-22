"""Key core modules must have loggers configured."""
import logging


def test_expression_engine_has_logger():
    import data_graph_studio.core.expression_engine as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_formula_parser_has_logger():
    import data_graph_studio.core.formula_parser as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_filtering_has_logger():
    import data_graph_studio.core.filtering as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_cache_has_logger():
    import data_graph_studio.core.cache as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_comparison_manager_has_logger():
    import data_graph_studio.core.comparison_manager as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_marking_has_logger():
    import data_graph_studio.core.marking as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_annotation_controller_has_logger():
    import data_graph_studio.core.annotation_controller as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_dashboard_controller_has_logger():
    import data_graph_studio.core.dashboard_controller as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_profile_store_has_logger():
    import data_graph_studio.core.profile_store as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_project_has_logger():
    import data_graph_studio.core.project as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_undo_manager_has_logger():
    import data_graph_studio.core.undo_manager as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)


def test_statistics_has_logger():
    import data_graph_studio.core.statistics as m
    assert hasattr(m, 'logger')
    assert isinstance(m.logger, logging.Logger)
