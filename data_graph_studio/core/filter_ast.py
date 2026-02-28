from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import polars as pl


@dataclass(frozen=True)
class PredicateNode:
    column: str
    operator: str
    value: Any = None
    case_sensitive: bool = True


@dataclass(frozen=True)
class AndNode:
    children: List["FilterNode"] = field(default_factory=list)


@dataclass(frozen=True)
class OrNode:
    children: List["FilterNode"] = field(default_factory=list)


@dataclass(frozen=True)
class NotNode:
    child: "FilterNode"


FilterNode = PredicateNode | AndNode | OrNode | NotNode


@dataclass
class FilterPresetStore:
    """In-memory AST preset store with serialization support."""

    _presets: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    def save(self, name: str, node: Optional[FilterNode]) -> None:
        if not name:
            raise ValueError("Preset name is required")
        self._presets[name] = node_to_dict(node)

    def load(self, name: str) -> Optional[FilterNode]:
        data = self._presets.get(name)
        return node_from_dict(data)

    def remove(self, name: str) -> None:
        self._presets.pop(name, None)

    def list_names(self) -> List[str]:
        return sorted(self._presets.keys())

    def to_dict(self) -> Dict[str, Dict[str, Any]]:
        return dict(self._presets)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Dict[str, Any]]]) -> "FilterPresetStore":
        inst = cls()
        if data:
            inst._presets = dict(data)
        return inst


def predicate_to_expr(node: PredicateNode) -> pl.Expr:
    col = pl.col(node.column)
    op = node.operator

    if op == "eq":
        return col == node.value
    if op == "ne":
        return col != node.value
    if op == "gt":
        return col > node.value
    if op == "lt":
        return col < node.value
    if op == "ge":
        return col >= node.value
    if op == "le":
        return col <= node.value
    if op == "contains":
        target = col.cast(pl.Utf8)
        value = str(node.value)
        if not node.case_sensitive:
            target = target.str.to_lowercase()
            value = value.lower()
        return target.str.contains(value)
    if op == "startswith":
        target = col.cast(pl.Utf8)
        value = str(node.value)
        if not node.case_sensitive:
            target = target.str.to_lowercase()
            value = value.lower()
        return target.str.starts_with(value)
    if op == "endswith":
        target = col.cast(pl.Utf8)
        value = str(node.value)
        if not node.case_sensitive:
            target = target.str.to_lowercase()
            value = value.lower()
        return target.str.ends_with(value)
    if op == "in":
        values = list(node.value) if isinstance(node.value, (list, tuple, set)) else [node.value]
        return col.is_in(values)
    if op == "not_in":
        values = list(node.value) if isinstance(node.value, (list, tuple, set)) else [node.value]
        return ~col.is_in(values)
    if op == "isnull":
        return col.is_null()
    if op == "notnull":
        return col.is_not_null()

    raise ValueError(f"Unknown filter operator: {op}")


def node_to_expr(node: Optional[FilterNode]) -> Optional[pl.Expr]:
    if node is None:
        return None
    if isinstance(node, PredicateNode):
        return predicate_to_expr(node)
    if isinstance(node, NotNode):
        expr = node_to_expr(node.child)
        return None if expr is None else ~expr
    if isinstance(node, AndNode):
        expr: Optional[pl.Expr] = None
        for child in node.children:
            c_expr = node_to_expr(child)
            if c_expr is None:
                continue
            expr = c_expr if expr is None else (expr & c_expr)
        return expr
    if isinstance(node, OrNode):
        expr: Optional[pl.Expr] = None
        for child in node.children:
            c_expr = node_to_expr(child)
            if c_expr is None:
                continue
            expr = c_expr if expr is None else (expr | c_expr)
        return expr
    raise TypeError(f"Unknown node type: {type(node)!r}")


def apply_filter_ast(df: pl.DataFrame, node: Optional[FilterNode]) -> pl.DataFrame:
    expr = node_to_expr(node)
    if expr is None:
        return df
    return df.filter(expr)


def node_to_dict(node: Optional[FilterNode]) -> Optional[Dict[str, Any]]:
    if node is None:
        return None
    if isinstance(node, PredicateNode):
        return {
            "type": "predicate",
            "column": node.column,
            "operator": node.operator,
            "value": node.value,
            "case_sensitive": node.case_sensitive,
        }
    if isinstance(node, AndNode):
        return {"type": "and", "children": [node_to_dict(c) for c in node.children]}
    if isinstance(node, OrNode):
        return {"type": "or", "children": [node_to_dict(c) for c in node.children]}
    if isinstance(node, NotNode):
        return {"type": "not", "child": node_to_dict(node.child)}
    raise TypeError(f"Unknown node type: {type(node)!r}")


def node_from_dict(data: Optional[Dict[str, Any]]) -> Optional[FilterNode]:
    if data is None:
        return None
    t = data.get("type")
    if t == "predicate":
        return PredicateNode(
            column=data.get("column", ""),
            operator=data.get("operator", "eq"),
            value=data.get("value"),
            case_sensitive=bool(data.get("case_sensitive", True)),
        )
    if t == "and":
        return AndNode(children=[node_from_dict(c) for c in data.get("children", []) if c is not None])
    if t == "or":
        return OrNode(children=[node_from_dict(c) for c in data.get("children", []) if c is not None])
    if t == "not":
        child = node_from_dict(data.get("child"))
        if child is None:
            raise ValueError("NOT node requires a child")
        return NotNode(child=child)
    raise ValueError(f"Unknown node type: {t}")
