"""Tests for indexio.graph — code structure graph for graph-RAG."""
from __future__ import annotations

from pathlib import Path

import pytest

from indexio.graph import (
    CodeGraph,
    Edge,
    SymbolNode,
    build_file_graph,
    build_project_graph,
    expand_results_with_graph,
)


SAMPLE_SOURCE = '''\
"""Sample module."""

import os
from pathlib import Path


def helper():
    """A helper function."""
    return 42


def main():
    """Main entry point."""
    result = helper()
    path = Path(".")
    return result


class Service:
    """A service class."""

    def run(self):
        result = helper()
        return result

    def stop(self):
        pass
'''


SAMPLE_INHERITANCE = '''\
class Base:
    def method(self):
        pass

class Child(Base):
    def method(self):
        return super().method()
'''


# ---- SymbolNode and Edge dataclasses ----------------------------------------

def test_symbol_node_fields() -> None:
    node = SymbolNode(
        id="f.py::foo",
        name="foo",
        qualified_name="f.foo",
        symbol_type="function",
        file_path="f.py",
        start_line=1,
        end_line=3,
    )
    assert node.id == "f.py::foo"
    assert node.parent_id is None
    assert node.language == "python"


def test_edge_fields() -> None:
    edge = Edge(source="a", target="b", relation="calls")
    assert edge.source == "a"
    assert edge.relation == "calls"


# ---- CodeGraph basic operations ---------------------------------------------

def test_code_graph_add_and_lookup() -> None:
    g = CodeGraph()
    node = SymbolNode(
        id="x.py::foo", name="foo", qualified_name="x.foo",
        symbol_type="function", file_path="x.py",
        start_line=1, end_line=5,
    )
    g.add_node(node)
    assert "x.py::foo" in g.nodes
    assert g.nodes["x.py::foo"].name == "foo"


def test_code_graph_add_edge() -> None:
    g = CodeGraph()
    g.add_edge("a", "b", "calls")
    assert len(g.edges) == 1
    assert g.edges[0].relation == "calls"


def test_neighbors_both_directions() -> None:
    g = CodeGraph()
    g.add_edge("a", "b", "calls")
    g.add_edge("c", "a", "imports")
    assert "b" in g.neighbors("a", direction="out")
    assert "c" in g.neighbors("a", direction="in")
    both = g.neighbors("a", direction="both")
    assert "b" in both
    assert "c" in both


def test_neighbors_filter_by_relation() -> None:
    g = CodeGraph()
    g.add_edge("a", "b", "calls")
    g.add_edge("a", "c", "imports")
    assert g.neighbors("a", relation="calls") == ["b"]
    assert g.neighbors("a", relation="imports") == ["c"]


# ---- Subgraph extraction ----------------------------------------------------

def test_subgraph_single_hop() -> None:
    g = CodeGraph()
    for name in ("a", "b", "c", "d"):
        g.add_node(SymbolNode(
            id=name, name=name, qualified_name=name,
            symbol_type="function", file_path="f.py",
            start_line=1, end_line=1,
        ))
    g.add_edge("a", "b", "calls")
    g.add_edge("b", "c", "calls")
    g.add_edge("c", "d", "calls")

    sub = g.subgraph({"a"}, max_hops=1)
    assert "a" in sub.nodes
    assert "b" in sub.nodes
    assert "c" not in sub.nodes  # 2 hops away


def test_subgraph_two_hops() -> None:
    g = CodeGraph()
    for name in ("a", "b", "c", "d"):
        g.add_node(SymbolNode(
            id=name, name=name, qualified_name=name,
            symbol_type="function", file_path="f.py",
            start_line=1, end_line=1,
        ))
    g.add_edge("a", "b", "calls")
    g.add_edge("b", "c", "calls")
    g.add_edge("c", "d", "calls")

    sub = g.subgraph({"a"}, max_hops=2)
    assert "c" in sub.nodes
    assert "d" not in sub.nodes


# ---- Serialization ----------------------------------------------------------

def test_to_dict_and_from_dict_roundtrip() -> None:
    g = CodeGraph()
    g.add_node(SymbolNode(
        id="f.py::foo", name="foo", qualified_name="mod.foo",
        symbol_type="function", file_path="f.py",
        start_line=1, end_line=5, docstring="A function.",
    ))
    g.add_edge("f.py::foo", "f.py::bar", "calls")

    data = g.to_dict()
    restored = CodeGraph.from_dict(data)
    assert "f.py::foo" in restored.nodes
    assert restored.nodes["f.py::foo"].docstring == "A function."
    assert len(restored.edges) == 1
    assert restored.edges[0].relation == "calls"


def test_to_json_is_valid() -> None:
    import json
    g = CodeGraph()
    g.add_node(SymbolNode(
        id="x", name="x", qualified_name="x",
        symbol_type="function", file_path="x.py",
        start_line=1, end_line=1,
    ))
    raw = g.to_json(indent=2)
    parsed = json.loads(raw)
    assert "nodes" in parsed
    assert "edges" in parsed


# ---- build_file_graph -------------------------------------------------------

def test_build_file_graph_finds_functions() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    names = {n.name for n in graph.nodes.values()}
    assert "helper" in names
    assert "main" in names
    assert "Service" in names


def test_build_file_graph_finds_methods() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    names = {n.name for n in graph.nodes.values()}
    assert "run" in names
    assert "stop" in names


def test_build_file_graph_module_node() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    mod_id = "sample.py::<module>"
    assert mod_id in graph.nodes
    assert graph.nodes[mod_id].symbol_type == "module"


def test_build_file_graph_containment_edges() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    contains_targets = [
        e.target for e in graph.edges if e.relation == "contains"
    ]
    assert "sample.py::helper" in contains_targets
    assert "sample.py::Service" in contains_targets


def test_build_file_graph_call_edges() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    call_edges = [e for e in graph.edges if e.relation == "calls"]
    # main() calls helper()
    main_calls = [
        e.target for e in call_edges if e.source == "sample.py::main"
    ]
    assert "sample.py::helper" in main_calls


def test_build_file_graph_import_edges() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    import_edges = [e for e in graph.edges if e.relation == "imports"]
    import_targets = [e.target for e in import_edges]
    assert "os" in import_targets
    assert "pathlib.Path" in import_targets


def test_build_file_graph_inheritance_edges() -> None:
    graph = build_file_graph(SAMPLE_INHERITANCE, "inh.py")
    inherits_edges = [e for e in graph.edges if e.relation == "inherits"]
    assert len(inherits_edges) == 1
    assert inherits_edges[0].source == "inh.py::Child"
    assert inherits_edges[0].target == "inh.py::Base"


def test_build_file_graph_captures_docstrings() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    helper = graph.nodes.get("sample.py::helper")
    assert helper is not None
    assert helper.docstring == "A helper function."


def test_build_file_graph_syntax_error_returns_empty() -> None:
    graph = build_file_graph("def broken(", "bad.py")
    assert len(graph.nodes) == 0


def test_build_file_graph_custom_module_name() -> None:
    graph = build_file_graph(
        "def foo(): pass", "src/utils.py", module_name="mylib.utils",
    )
    foo = graph.nodes.get("src/utils.py::foo")
    assert foo is not None
    assert foo.qualified_name == "mylib.utils.foo"


# ---- build_project_graph ---------------------------------------------------

def test_build_project_graph(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def greet(): return 'hi'\n", encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "from a import greet\ndef main(): greet()\n", encoding="utf-8",
    )
    graph = build_project_graph(
        tmp_path, [tmp_path / "a.py", tmp_path / "b.py"],
    )
    assert "a.py::greet" in graph.nodes
    assert "b.py::main" in graph.nodes


def test_build_project_graph_cross_file_calls(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text(
        "def shared(): pass\n", encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        "def caller(): shared()\n", encoding="utf-8",
    )
    graph = build_project_graph(
        tmp_path, [tmp_path / "a.py", tmp_path / "b.py"],
    )
    # Cross-file call resolution
    call_edges = [
        e for e in graph.edges
        if e.relation == "calls" and e.source == "b.py::caller"
    ]
    targets = [e.target for e in call_edges]
    assert "a.py::shared" in targets


def test_build_project_graph_skips_non_python(tmp_path: Path) -> None:
    (tmp_path / "readme.md").write_text("# Hi\n", encoding="utf-8")
    graph = build_project_graph(tmp_path, [tmp_path / "readme.md"])
    assert len(graph.nodes) == 0


def test_build_project_graph_skips_missing(tmp_path: Path) -> None:
    graph = build_project_graph(
        tmp_path, [tmp_path / "nonexistent.py"],
    )
    assert len(graph.nodes) == 0


# ---- expand_results_with_graph ---------------------------------------------

def test_expand_results_with_graph() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    results = [
        {
            "source_path": "sample.py",
            "symbol_name": "main",
            "snippet": "def main(): ...",
        },
    ]
    expanded = expand_results_with_graph(results, graph, max_hops=1)
    # Should have original + graph-expanded results
    assert len(expanded) > len(results)
    extra = [r for r in expanded if r.get("graph_expanded")]
    assert len(extra) > 0


def test_expand_results_no_match_returns_original() -> None:
    graph = CodeGraph()
    results = [{"source_path": "x.py", "snippet": "..."}]
    expanded = expand_results_with_graph(results, graph)
    assert expanded == results


def test_expand_results_respects_max_extra() -> None:
    graph = build_file_graph(SAMPLE_SOURCE, "sample.py")
    results = [
        {
            "source_path": "sample.py",
            "symbol_name": "<module>",
            "snippet": "...",
        },
    ]
    expanded = expand_results_with_graph(
        results, graph, max_hops=2, max_extra=2,
    )
    extra = [r for r in expanded if r.get("graph_expanded")]
    assert len(extra) <= 2
