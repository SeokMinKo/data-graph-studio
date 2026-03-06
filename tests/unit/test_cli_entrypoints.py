import argparse

from data_graph_studio import cli
from data_graph_studio import __main__ as entry


def test_cli_main_without_command_returns_zero(monkeypatch):
    parser = cli.create_parser()

    monkeypatch.setattr(parser, "parse_args", lambda: argparse.Namespace(command=None))
    monkeypatch.setattr(cli, "create_parser", lambda: parser)

    assert cli.main() == 0


def test_cli_main_unknown_command_returns_one(monkeypatch):
    parser = cli.create_parser()

    monkeypatch.setattr(
        parser, "parse_args", lambda: argparse.Namespace(command="unknown")
    )
    monkeypatch.setattr(cli, "create_parser", lambda: parser)

    assert cli.main() == 1


def test_cmd_server_runtime_error_returns_one(monkeypatch):
    from data_graph_studio import api_server

    def _raise_runtime_error(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(api_server, "run_server", _raise_runtime_error)

    args = argparse.Namespace(host="127.0.0.1", port=8080)
    assert cli.cmd_server(args) == 1


def test_entry_parse_args_debug(monkeypatch):
    monkeypatch.setattr("sys.argv", ["prog", "--debug"])
    args = entry.parse_args()
    assert args.debug is True
