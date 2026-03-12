# Query The Index

## Basic query

```bash
indexio query "semantic search"
```

## Filter by corpus

```bash
indexio query --corpus docs "semantic search"
```

## Adjust number of results

```bash
indexio query --k 12 "semantic search"
```

## JSON output

```bash
indexio query --json "semantic search"
```

## Python API

```python
from indexio import query_index, query_index_multi

# Single query
result = query_index(
    config_path=".indexio/config.yaml",
    root="/path/to/project",
    query="embeddings",
    corpus="docs",
    k=8,
)

# Multi-query with deduplication
result = query_index_multi(
    config_path=".indexio/config.yaml",
    root="/path/to/project",
    queries=["embeddings", "vector search"],
    k=5,
)
```
