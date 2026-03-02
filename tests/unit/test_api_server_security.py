import pytest

from data_graph_studio import api_server


pytestmark = pytest.mark.skipif(
    not getattr(api_server, "FASTAPI_AVAILABLE", False),
    reason="FastAPI not available",
)


class _DummyRequest:
    def __init__(self, headers=None):
        self.headers = headers or {}


def test_require_api_token_no_env_allows(monkeypatch):
    monkeypatch.delenv("DGS_API_TOKEN", raising=False)

    req = _DummyRequest(headers={})

    # should not raise
    api_server._require_api_token(req)


def test_require_api_token_rejects_missing_token(monkeypatch):
    monkeypatch.setenv("DGS_API_TOKEN", "secret-token")

    req = _DummyRequest(headers={})

    with pytest.raises(Exception) as exc:
        api_server._require_api_token(req)

    assert "Unauthorized" in str(exc.value)


def test_require_api_token_accepts_matching_token(monkeypatch):
    monkeypatch.setenv("DGS_API_TOKEN", "secret-token")

    req = _DummyRequest(headers={api_server.API_AUTH_HEADER: "secret-token"})

    # should not raise
    api_server._require_api_token(req)
