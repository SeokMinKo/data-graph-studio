import importlib

from data_graph_studio.core import updater


def test_get_current_version_returns_fallback_when_metadata_missing(monkeypatch):
    """Regression: source-run environments may not have package metadata installed."""

    metadata = importlib.import_module("importlib.metadata")

    def _raise_not_found(_dist_name: str) -> str:
        raise metadata.PackageNotFoundError("data-graph-studio")

    monkeypatch.setattr(metadata, "version", _raise_not_found)

    assert updater.get_current_version() == "0.0.0"
