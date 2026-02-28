from __future__ import annotations

import polars as pl

from data_graph_studio.core.filter_ast import (
    AndNode,
    NotNode,
    OrNode,
    PredicateNode,
    apply_filter_ast,
    node_from_dict,
    node_to_dict,
    FilterPresetStore,
)


def test_filter_ast_and_or_not_predicates():
    df = pl.DataFrame(
        {
            "a": [1, 2, 3, 4],
            "b": ["foo", "bar", "food", "baz"],
            "flag": [True, False, True, False],
        }
    )

    ast = AndNode(
        children=[
            PredicateNode("a", "ge", 2),
            OrNode(
                children=[
                    PredicateNode("b", "contains", "foo"),
                    PredicateNode("flag", "eq", False),
                ]
            ),
            NotNode(PredicateNode("a", "eq", 4)),
        ]
    )

    out = apply_filter_ast(df, ast)
    assert out["a"].to_list() == [2, 3]


def test_filter_ast_serialization_roundtrip():
    ast = OrNode(
        children=[
            PredicateNode("x", "in", [1, 2, 3]),
            NotNode(PredicateNode("name", "startswith", "tmp", case_sensitive=False)),
        ]
    )

    data = node_to_dict(ast)
    restored = node_from_dict(data)

    assert node_to_dict(restored) == data


def test_filter_preset_store_save_load():
    store = FilterPresetStore()
    ast = PredicateNode("col", "eq", 42)

    store.save("answer", ast)
    loaded = store.load("answer")

    assert node_to_dict(loaded) == node_to_dict(ast)
    assert store.list_names() == ["answer"]
