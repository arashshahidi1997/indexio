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

## `query_index(*, config_path, root, query, store=None, prefer_canonical=False, corpus=None, k=4) → dict`

Run a similarity search. Returns a dict with `results` list, each containing `corpus`, `source_id`, `source_path`, `chunk_index`, and `snippet`.

## `query_index_multi(*, config_path, root, queries, store=None, prefer_canonical=False, corpus=None, k=4) → dict`

Run multiple queries and merge results with deduplication by `(source_path, chunk_index)`.

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
