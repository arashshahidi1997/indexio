# indexio

Lightweight semantic indexing and retrieval for project knowledge sources.

Indexes document sources (markdown, code, etc.) into a ChromaDB vector store and provides semantic search. Standalone library — no knowledge of projio or other ecosystem packages.

## Install

```bash
pip install indexio
# or editable from source:
make dev
```

## Quick start

```bash
# Write a starter config into your project
indexio init-config --root . --output infra/indexio/config.yaml

# Build the index
indexio build --config infra/indexio/config.yaml --root .

# Query
indexio query --config infra/indexio/config.yaml --root . "how does authentication work"

# Show store status
indexio status --config infra/indexio/config.yaml --root .
```

## Python API

```python
from indexio import load_indexio_config, build_index, query_index

cfg = load_indexio_config("infra/indexio/config.yaml", root="/path/to/project")
build_index(config_path="infra/indexio/config.yaml", root="/path/to/project")
results = query_index(config_path="infra/indexio/config.yaml", root="/path/to/project", query="embeddings")
```
