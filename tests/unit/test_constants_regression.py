"""Regression tests for constants and API fixes from Round 10.

Ensures DEFAULT_SCHEME_NAME value is stable and FilteringManager
uses it as the default scheme name.
"""
from data_graph_studio.core.constants import DEFAULT_SCHEME_NAME


def test_default_scheme_name_value():
    """DEFAULT_SCHEME_NAME must equal 'Page' — changing it would break FilteringManager state."""
    assert DEFAULT_SCHEME_NAME == "Page"


def test_default_scheme_name_is_string():
    assert isinstance(DEFAULT_SCHEME_NAME, str)


def test_filtering_manager_uses_default_scheme_name():
    """FilteringManager should create a default scheme named DEFAULT_SCHEME_NAME."""
    from data_graph_studio.core.filtering import FilteringManager
    fm = FilteringManager()
    assert DEFAULT_SCHEME_NAME in fm.get_scheme_names()
    assert fm.active_scheme == DEFAULT_SCHEME_NAME
