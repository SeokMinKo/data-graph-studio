def test_ipc_server_has_no_qt_import():
    import ast
    import pathlib
    src = pathlib.Path("data_graph_studio/core/ipc_server.py").read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert "PySide6" not in node.module
