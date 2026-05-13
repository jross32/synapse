"""Contract #20 — project dependencies."""

from __future__ import annotations

import pytest

from synapse_daemon.dependencies import reverse_dependents, topological_order
from synapse_daemon.errors import SynapseError


def test_linear_chain() -> None:
    graph = {"a": ["b"], "b": ["c"], "c": []}
    order = topological_order(graph, roots=["a"])
    assert order == ["c", "b", "a"]


def test_diamond() -> None:
    graph = {"a": ["b", "c"], "b": ["d"], "c": ["d"], "d": []}
    order = topological_order(graph, roots=["a"])
    # d before b and c; b and c before a.
    assert order.index("d") < order.index("b")
    assert order.index("d") < order.index("c")
    assert order.index("b") < order.index("a")
    assert order.index("c") < order.index("a")


def test_only_reachable_subgraph_included() -> None:
    graph = {"a": ["b"], "b": [], "x": ["y"], "y": []}
    order = topological_order(graph, roots=["a"])
    assert order == ["b", "a"]
    assert "x" not in order
    assert "y" not in order


def test_cycle_detected() -> None:
    graph = {"a": ["b"], "b": ["a"]}
    with pytest.raises(SynapseError) as exc:
        topological_order(graph, roots=["a"])
    assert exc.value.envelope.code == "project.dependency_cycle"
    assert exc.value.status == 409


def test_missing_node_raises_not_found() -> None:
    graph = {"a": ["b"]}  # b is not declared
    with pytest.raises(SynapseError) as exc:
        topological_order(graph, roots=["a"])
    assert exc.value.envelope.code == "project.not_found"


def test_reverse_dependents() -> None:
    graph = {"a": ["b", "c"], "b": ["c"], "c": []}
    rev = reverse_dependents(graph)
    assert rev["b"] == ["a"]
    assert rev["c"] == ["a", "b"]
