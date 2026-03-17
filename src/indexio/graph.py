"""Code structure graph for graph-RAG.

Builds a lightweight in-memory graph of code symbols (functions, classes,
methods) and their relationships (imports, calls, containment).  The graph
can be serialized to JSON and used for:

  - Graph-augmented retrieval: expand vector search results with
    structurally related symbols (callers, callees, parent class, etc.)
  - Dependency-aware context: when retrieving a function, also pull its
    imports and the classes it belongs to.
  - Navigation: answer "what depends on X?" without re-parsing.

The graph is built from Python's stdlib ``ast`` module (zero extra deps).
Optional tree-sitter support can be added for multi-language graphs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class SymbolNode:
    """A code symbol in the graph."""

    id: str  # e.g. "src/utils.py::parse_config"
    name: str  # e.g. "parse_config"
    qualified_name: str  # e.g. "utils.parse_config"
    symbol_type: str  # function | class | method | module
    file_path: str  # relative path
    start_line: int
    end_line: int
    language: str = "python"
    parent_id: str | None = None  # for methods: the class node id
    docstring: str | None = None


@dataclass
class Edge:
    """A directed relationship between two symbols."""

    source: str  # symbol id
    target: str  # symbol id
    relation: str  # imports | calls | contains | inherits


@dataclass
class CodeGraph:
    """In-memory code structure graph."""

    nodes: dict[str, SymbolNode] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)

    def add_node(self, node: SymbolNode) -> None:
        self.nodes[node.id] = node

    def add_edge(
        self, source: str, target: str, relation: str,
    ) -> None:
        self.edges.append(Edge(source, target, relation))

    def neighbors(
        self,
        node_id: str,
        relation: str | None = None,
        direction: str = "both",
    ) -> list[str]:
        """Return neighbor node IDs.

        Args:
            node_id: The node to find neighbors for.
            relation: Optional filter by edge relation type.
            direction: "out", "in", or "both".
        """
        result: list[str] = []
        for edge in self.edges:
            if relation and edge.relation != relation:
                continue
            if direction in ("out", "both") and edge.source == node_id:
                result.append(edge.target)
            if direction in ("in", "both") and edge.target == node_id:
                result.append(edge.source)
        return result

    def subgraph(self, node_ids: set[str], max_hops: int = 1) -> CodeGraph:
        """Return a subgraph containing *node_ids* and their neighbors."""
        expanded = set(node_ids)
        frontier = set(node_ids)
        for _ in range(max_hops):
            next_frontier: set[str] = set()
            for nid in frontier:
                for neighbor in self.neighbors(nid):
                    if neighbor not in expanded:
                        next_frontier.add(neighbor)
                        expanded.add(neighbor)
            frontier = next_frontier

        sub = CodeGraph()
        for nid in expanded:
            if nid in self.nodes:
                sub.add_node(self.nodes[nid])
        for edge in self.edges:
            if edge.source in expanded and edge.target in expanded:
                sub.edges.append(edge)
        return sub

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": {
                nid: {
                    "name": n.name,
                    "qualified_name": n.qualified_name,
                    "symbol_type": n.symbol_type,
                    "file_path": n.file_path,
                    "start_line": n.start_line,
                    "end_line": n.end_line,
                    "language": n.language,
                    "parent_id": n.parent_id,
                    "docstring": n.docstring,
                }
                for nid, n in self.nodes.items()
            },
            "edges": [
                {
                    "source": e.source,
                    "target": e.target,
                    "relation": e.relation,
                }
                for e in self.edges
            ],
        }

    def to_json(self, **kwargs: Any) -> str:
        return json.dumps(self.to_dict(), **kwargs)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CodeGraph:
        graph = cls()
        for nid, raw in data.get("nodes", {}).items():
            graph.add_node(SymbolNode(
                id=nid,
                name=raw["name"],
                qualified_name=raw["qualified_name"],
                symbol_type=raw["symbol_type"],
                file_path=raw["file_path"],
                start_line=raw["start_line"],
                end_line=raw["end_line"],
                language=raw.get("language", "python"),
                parent_id=raw.get("parent_id"),
                docstring=raw.get("docstring"),
            ))
        for raw_edge in data.get("edges", []):
            graph.add_edge(
                raw_edge["source"], raw_edge["target"], raw_edge["relation"],
            )
        return graph


# ---------------------------------------------------------------------------
# Graph construction from Python AST
# ---------------------------------------------------------------------------

def _node_id(file_path: str, name: str) -> str:
    return f"{file_path}::{name}"


def _get_docstring(node) -> str | None:
    """Extract docstring from an ast node, if present."""
    import ast as _ast
    return _ast.get_docstring(node)


def _extract_calls(node) -> list[str]:
    """Extract function/method call names from an ast node body."""
    import ast as _ast

    calls: list[str] = []
    for child in _ast.walk(node):
        if isinstance(child, _ast.Call):
            if isinstance(child.func, _ast.Name):
                calls.append(child.func.id)
            elif isinstance(child.func, _ast.Attribute):
                calls.append(child.func.attr)
    return calls


def _extract_imports(tree) -> list[tuple[str, str | None]]:
    """Extract import names from an ast module.

    Returns list of (module_or_name, alias_or_None).
    """
    import ast as _ast

    imports: list[tuple[str, str | None]] = []
    for node in _ast.iter_child_nodes(tree):
        if isinstance(node, _ast.Import):
            for alias in node.names:
                imports.append((alias.name, alias.asname))
        elif isinstance(node, _ast.ImportFrom):
            mod = node.module or ""
            for alias in node.names:
                imports.append(
                    (f"{mod}.{alias.name}", alias.asname),
                )
    return imports


def build_file_graph(
    source: str,
    file_path: str,
    *,
    module_name: str | None = None,
) -> CodeGraph:
    """Build a CodeGraph from a single Python source file.

    Args:
        source: Python source code text.
        file_path: Relative file path (used in node IDs).
        module_name: Optional module name prefix for qualified names.
    """
    import ast as _ast

    graph = CodeGraph()

    try:
        tree = _ast.parse(source)
    except SyntaxError:
        return graph

    prefix = module_name or Path(file_path).stem

    # Module node
    mod_id = _node_id(file_path, "<module>")
    graph.add_node(SymbolNode(
        id=mod_id,
        name=prefix,
        qualified_name=prefix,
        symbol_type="module",
        file_path=file_path,
        start_line=1,
        end_line=len(source.splitlines()),
        docstring=_get_docstring(tree),
    ))

    # Imports
    for imp_name, _alias in _extract_imports(tree):
        graph.add_edge(mod_id, imp_name, "imports")

    # Top-level symbols
    for node in _ast.iter_child_nodes(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            func_id = _node_id(file_path, node.name)
            graph.add_node(SymbolNode(
                id=func_id,
                name=node.name,
                qualified_name=f"{prefix}.{node.name}",
                symbol_type="function",
                file_path=file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                docstring=_get_docstring(node),
            ))
            graph.add_edge(mod_id, func_id, "contains")

            # Calls from this function
            for call_name in _extract_calls(node):
                call_target = _node_id(file_path, call_name)
                graph.add_edge(func_id, call_target, "calls")

        elif isinstance(node, _ast.ClassDef):
            class_id = _node_id(file_path, node.name)
            graph.add_node(SymbolNode(
                id=class_id,
                name=node.name,
                qualified_name=f"{prefix}.{node.name}",
                symbol_type="class",
                file_path=file_path,
                start_line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                docstring=_get_docstring(node),
            ))
            graph.add_edge(mod_id, class_id, "contains")

            # Base classes
            for base in node.bases:
                if isinstance(base, _ast.Name):
                    base_id = _node_id(file_path, base.id)
                    graph.add_edge(class_id, base_id, "inherits")

            # Methods
            for child in _ast.iter_child_nodes(node):
                if isinstance(
                    child, (_ast.FunctionDef, _ast.AsyncFunctionDef)
                ):
                    method_name = f"{node.name}.{child.name}"
                    method_id = _node_id(file_path, method_name)
                    graph.add_node(SymbolNode(
                        id=method_id,
                        name=child.name,
                        qualified_name=f"{prefix}.{method_name}",
                        symbol_type="method",
                        file_path=file_path,
                        start_line=child.lineno,
                        end_line=child.end_lineno or child.lineno,
                        parent_id=class_id,
                        docstring=_get_docstring(child),
                    ))
                    graph.add_edge(class_id, method_id, "contains")

                    for call_name in _extract_calls(child):
                        call_target = _node_id(file_path, call_name)
                        graph.add_edge(method_id, call_target, "calls")

    return graph


def build_project_graph(
    root: Path,
    file_paths: list[Path],
) -> CodeGraph:
    """Build a merged CodeGraph from multiple Python files.

    Args:
        root: Project root for computing relative paths.
        file_paths: List of absolute or root-relative Python file paths.
    """
    merged = CodeGraph()
    for fpath in file_paths:
        abs_path = fpath if fpath.is_absolute() else root / fpath
        if not abs_path.exists() or not abs_path.suffix == ".py":
            continue
        try:
            source = abs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        rel = str(abs_path.relative_to(root))
        module_name = (
            rel.replace("/", ".").replace("\\", ".").removesuffix(".py")
        )
        file_graph = build_file_graph(
            source, rel, module_name=module_name,
        )
        for node in file_graph.nodes.values():
            merged.add_node(node)
        for edge in file_graph.edges:
            merged.edges.append(edge)

    # Resolve cross-file call edges: if a call target matches a known
    # node name in another file, add a cross-file edge.
    names_to_ids: dict[str, list[str]] = {}
    for nid, node in merged.nodes.items():
        names_to_ids.setdefault(node.name, []).append(nid)

    extra_edges: list[Edge] = []
    for edge in merged.edges:
        if edge.relation != "calls":
            continue
        if edge.target in merged.nodes:
            continue
        # Target is an unresolved name — look for matching node names
        target_name = edge.target.split("::")[-1]
        candidates = names_to_ids.get(target_name, [])
        for candidate_id in candidates:
            if candidate_id != edge.source:
                extra_edges.append(
                    Edge(edge.source, candidate_id, "calls")
                )
    merged.edges.extend(extra_edges)

    return merged


# ---------------------------------------------------------------------------
# Graph-augmented retrieval
# ---------------------------------------------------------------------------

def expand_results_with_graph(
    results: list[dict[str, Any]],
    graph: CodeGraph,
    *,
    max_hops: int = 1,
    max_extra: int = 5,
) -> list[dict[str, Any]]:
    """Expand vector search results with graph-connected symbols.

    For each result that has a ``source_path`` and ``symbol_name``, find
    the corresponding graph node and add its neighbors as extra context
    results (marked with ``graph_expanded: True``).

    Args:
        results: Original vector search results (list of dicts).
        graph: The code structure graph.
        max_hops: How many hops to expand from each result node.
        max_extra: Maximum number of extra results to add.

    Returns:
        The original results plus any graph-expanded results appended.
    """
    seed_ids: set[str] = set()
    for r in results:
        sp = r.get("source_path")
        sn = r.get("symbol_name")
        if sp and sn:
            nid = _node_id(sp, sn)
            if nid in graph.nodes:
                seed_ids.add(nid)

    if not seed_ids:
        return results

    sub = graph.subgraph(seed_ids, max_hops=max_hops)
    existing_keys = {
        (r.get("source_path"), r.get("symbol_name")) for r in results
    }

    extra: list[dict[str, Any]] = []
    for nid, node in sub.nodes.items():
        if nid in seed_ids:
            continue
        key = (node.file_path, node.name)
        if key in existing_keys:
            continue
        extra.append({
            "source_path": node.file_path,
            "symbol_name": node.name,
            "symbol_type": node.symbol_type,
            "language": node.language,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "graph_expanded": True,
            "snippet": (
                f"[graph-expanded] {node.symbol_type} "
                f"{node.qualified_name} "
                f"({node.file_path}:{node.start_line})"
            ),
        })
        if len(extra) >= max_extra:
            break

    return [*results, *extra]
