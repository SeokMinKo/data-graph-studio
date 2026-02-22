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
