# Python API Reference

## Public API

All public symbols are exported from the `indexio` package:

```python
from indexio import (
    IndexioConfig,
    StoreConfig,
    SourceConfig,
    load_indexio_config,
    build_index,
    sync_owned_sources,
    query_index,
    query_index_multi,
)
```

## `load_indexio_config(config_path, root) → IndexioConfig`

Load and parse a YAML config file. Resolves `includes` composition, validates stores and sources.

## `build_index(*, config_path, root, store=None, sources_filter=None) → dict`

Build or rebuild the Chroma index. Returns a summary dict with per-source stats.

- Full rebuild (default): clears the store before indexing.
- Partial rebuild: pass `sources_filter=["docs"]` to only rebuild specific sources.

## `query_index(*, config_path, root, query, store=None, prefer_canonical=False, corpus=None, symbol_type=None, k=4) → dict`

Run a similarity search. Returns a dict with `results` list, each containing `corpus`, `source_id`, `source_path`, `chunk_index`, and `snippet`. When code-aware chunkers are used, results also include `symbol_name`, `symbol_type`, `language`, `start_line`, `end_line`.

Optional `symbol_type` filter restricts results to specific symbol types (e.g. `"function"`, `"class"`, `"method"`).

## `query_index_multi(*, config_path, root, queries, store=None, prefer_canonical=False, corpus=None, symbol_type=None, k=4) → dict`

Run multiple queries and merge results with deduplication by `(source_path, chunk_index)`.

## `get_chunker(name, *, chunk_size=1000, chunk_overlap=200, options=None) → Chunker`

Return a chunker backend instance by name (`"text"`, `"ast"`, or `"code"`). `None` defaults to `"text"`.

## `build_file_graph(source, file_path, *, module_name=None) → CodeGraph`

Build a code structure graph from a single Python source file using stdlib `ast`. The graph contains symbol nodes (functions, classes, methods) and edges (contains, calls, imports, inherits).

## `build_project_graph(root, file_paths) → CodeGraph`

Build a merged code graph from multiple Python files. Resolves cross-file call edges by matching function names across files.

## `CodeGraph`

In-memory code structure graph with methods:

- `add_node(node)` / `add_edge(source, target, relation)`
- `neighbors(node_id, relation=None, direction="both")` — find connected nodes
- `subgraph(node_ids, max_hops=1)` — extract a neighborhood subgraph
- `to_dict()` / `to_json()` / `from_dict(data)` — serialization

## `sync_owned_sources(config_path, root, *, owned_source_ids, sources, force_init=False, template=None) → OwnedSourcesSyncResult`

Register sources in a shared config. Only sources whose `id` is in `owned_source_ids` are modified; all others are preserved.

## Dataclasses

### `IndexioConfig`

| Field | Type |
|-------|------|
| `root` | `Path` |
| `config_path` | `Path` |
| `embedding_model` | `str` |
| `chunk_size_chars` | `int` |
| `chunk_overlap_chars` | `int` |
| `default_store` | `str` |
| `canonical_store` | `str \| None` |
| `stores` | `dict[str, StoreConfig]` |
| `sources` | `list[SourceConfig]` |

### `StoreConfig`

| Field | Type |
|-------|------|
| `name` | `str` |
| `persist_directory` | `Path` |
| `read_only` | `bool` |
| `description` | `str \| None` |

### `SourceConfig`

| Field | Type |
|-------|------|
| `id` | `str` |
| `corpus` | `str` |
| `path` | `str \| None` |
| `glob` | `str \| None` |
| `exclude` | `tuple[str, ...]` |
| `chunker` | `str \| None` |
| `chunker_options` | `dict \| None` |
