"""Project dependencies (Contract #20).

Manifest field ``requires: [other-project-id]`` declares hard prerequisites.
This module provides:

  • Topological ordering of a dependency graph.
  • Cycle detection (raises with a clear ``project.dependency_cycle`` error).
  • Reverse lookup (which projects require X?) for cascading stop confirmations.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from collections import defaultdict, deque

from .errors import SynapseError


def topological_order(requires: Mapping[str, Iterable[str]], roots: Iterable[str]) -> list[str]:
    """Return the launch order for ``roots`` plus all transitive dependencies.

    Args:
        requires: project_id → list of project_ids that must launch first.
                  All project_ids in either keys or values must appear in the
                  graph; missing ones cause :class:`SynapseError` (``project.not_found``).
        roots: the projects the user explicitly asked to launch.

    Returns:
        Project IDs in launch order — dependencies before dependents. Each
        project appears at most once.

    Raises:
        SynapseError(``project.dependency_cycle``) if a cycle is reached.
    """

    # Validate that every referenced node is in the graph.
    graph: dict[str, set[str]] = {k: set(v) for k, v in requires.items()}
    for parent, deps in graph.items():
        for d in deps:
            if d not in graph:
                raise SynapseError(
                    code="project.not_found",
                    message=f"Dependency '{d}' of '{parent}' is not registered.",
                    status=404,
                )

    # Compute the closure of roots (only the subgraph we care about).
    visited: set[str] = set()
    stack = list(roots)
    while stack:
        node = stack.pop()
        if node not in graph:
            raise SynapseError(
                code="project.not_found",
                message=f"Project '{node}' is not registered.",
                status=404,
            )
        if node in visited:
            continue
        visited.add(node)
        stack.extend(graph[node])

    # Kahn's algorithm restricted to ``visited``.
    in_degree: dict[str, int] = {n: 0 for n in visited}
    edges: dict[str, set[str]] = {n: set() for n in visited}
    for parent in visited:
        for dep in graph[parent]:
            edges[dep].add(parent)
            in_degree[parent] += 1

    queue: deque[str] = deque(sorted(n for n, d in in_degree.items() if d == 0))
    order: list[str] = []
    while queue:
        node = queue.popleft()
        order.append(node)
        for child in sorted(edges[node]):
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    if len(order) != len(visited):
        unresolved = sorted(visited - set(order))
        raise SynapseError(
            code="project.dependency_cycle",
            message=f"Dependency cycle detected involving: {', '.join(unresolved)}",
            details={"involved": unresolved},
            status=409,
        )

    return order


def reverse_dependents(requires: Mapping[str, Iterable[str]]) -> dict[str, list[str]]:
    """Return ``project_id → [ids that require it]`` for cascading-stop UI."""

    rev: dict[str, list[str]] = defaultdict(list)
    for parent, deps in requires.items():
        for d in deps:
            rev[d].append(parent)
    return {k: sorted(v) for k, v in rev.items()}
