"""
ColumnDependencyGraph — DAG-based dependency tracking for computed columns.

PRD §6.7, FR-3.10

Provides cycle detection, topological sort, and cascade dependency tracking.
"""

from __future__ import annotations

from collections import deque
from typing import Dict, List, Optional, Set


class CycleDetectedError(Exception):
    """Raised when adding a column would create a circular dependency (FR-3.10)."""

    pass


class ColumnDependencyGraph:
    """
    Manages a Directed Acyclic Graph of computed column dependencies.

    Each node is a computed column name.
    An edge from A → B means "A depends on B" (A references B).

    Usage:
        graph = ColumnDependencyGraph()
        graph.add_column('power', {'voltage', 'current'})
        graph.add_column('power_norm', {'power'})
        order = graph.get_evaluation_order()  # ['voltage', 'current', 'power', 'power_norm'] (approx)
    """

    def __init__(self) -> None:
        # column_name → set of columns it depends on (its prerequisites)
        self._edges: Dict[str, Set[str]] = {}

    # ── Public API ────────────────────────────────────────────

    def add_column(self, name: str, dependencies: Set[str]) -> None:
        """
        Register a computed column with its dependencies.

        Raises CycleDetectedError if adding this column would create a cycle.
        """
        # Check for self-reference
        if name in dependencies:
            raise CycleDetectedError(f"Circular dependency detected: {name} → {name}")

        # Temporarily add and check for cycle
        old_deps = self._edges.get(name)
        self._edges[name] = set(dependencies)

        cycle_path = self._find_cycle(name)
        if cycle_path is not None:
            # Roll back
            if old_deps is not None:
                self._edges[name] = old_deps
            else:
                del self._edges[name]
            path_str = " → ".join(cycle_path)
            raise CycleDetectedError(f"Circular dependency detected: {path_str}")

    def remove_column(self, name: str) -> Set[str]:
        """
        Remove a column from the graph.

        Returns the set of columns that were depending on *name*
        (useful for cascade warnings).
        """
        dependents = self.get_dependents(name)
        self._edges.pop(name, None)
        # Also remove *name* from other columns' dependency sets
        for deps in self._edges.values():
            deps.discard(name)
        return dependents

    def has_cycle(self) -> bool:
        """Check if the current graph contains any cycle."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        for node in self._edges:
            if node not in visited:
                if self._dfs_has_cycle(node, visited, rec_stack):
                    return True
        return False

    def get_evaluation_order(self) -> List[str]:
        """
        Return columns in topological order (dependencies first).

        Raises CycleDetectedError if a cycle exists.
        """
        # Kahn's algorithm
        # Build in-degree map
        all_nodes = set(self._edges.keys())
        in_degree: Dict[str, int] = {n: 0 for n in all_nodes}

        for node, deps in self._edges.items():
            for dep in deps:
                if dep in all_nodes:
                    in_degree[node] += 1  # node depends on dep → node has +1 in-degree

        queue: deque[str] = deque()
        for node, degree in in_degree.items():
            if degree == 0:
                queue.append(node)

        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            # Find nodes that depend on `node`
            for other, deps in self._edges.items():
                if node in deps and other in in_degree:
                    in_degree[other] -= 1
                    if in_degree[other] == 0:
                        queue.append(other)

        if len(result) != len(all_nodes):
            raise CycleDetectedError("Circular dependency detected in graph")

        return result

    def get_dependents(self, name: str) -> Set[str]:
        """
        Return all columns that (transitively) depend on *name*.

        i.e. if name is deleted, these columns would be affected.
        """
        dependents: Set[str] = set()
        queue: deque[str] = deque([name])

        while queue:
            current = queue.popleft()
            for col, deps in self._edges.items():
                if current in deps and col not in dependents:
                    dependents.add(col)
                    queue.append(col)

        return dependents

    def get_dependencies(self, name: str) -> Set[str]:
        """Return the direct dependencies of *name*."""
        return set(self._edges.get(name, set()))

    def columns(self) -> Set[str]:
        """All registered column names."""
        return set(self._edges.keys())

    # ── Internal ──────────────────────────────────────────────

    def _find_cycle(self, start: str) -> Optional[List[str]]:
        """
        Find a cycle involving *start* using DFS.

        Returns the cycle path as a list, or None if no cycle.
        """
        visited: Set[str] = set()
        path: List[str] = []

        def dfs(node: str) -> Optional[List[str]]:
            if node in visited:
                return None
            if node in set(path):
                # Found cycle
                idx = path.index(node)
                return path[idx:] + [node]
            path.append(node)
            for dep in self._edges.get(node, set()):
                if dep in self._edges:  # only follow edges to registered columns
                    result = dfs(dep)
                    if result is not None:
                        return result
            path.pop()
            visited.add(node)
            return None

        return dfs(start)

    def _dfs_has_cycle(self, node: str, visited: Set[str], rec_stack: Set[str]) -> bool:
        """DFS helper for has_cycle()."""
        visited.add(node)
        rec_stack.add(node)

        for dep in self._edges.get(node, set()):
            if dep in self._edges:  # only registered nodes
                if dep not in visited:
                    if self._dfs_has_cycle(dep, visited, rec_stack):
                        return True
                elif dep in rec_stack:
                    return True

        rec_stack.discard(node)
        return False
