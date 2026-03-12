# Architecture

indexio is a lightweight semantic indexing and retrieval library organized into five modules.

## Pipeline

```
YAML Config → Load Sources → Read Files → Split into Chunks → Embed → Upsert to ChromaDB
```

## Modules

**config** — Loads and validates YAML configuration. Supports composition via `includes:` for merging configs from multiple ecosystem packages. Resolves stores and sources into typed dataclasses.

**build** — Reads files matched by source globs or paths, splits text with `RecursiveCharacterTextSplitter`, generates embeddings via HuggingFace, and upserts into ChromaDB in batches of 100. Supports full rebuild (clear + reindex) and partial rebuild (by source id).

**query** — Wraps ChromaDB similarity search with optional corpus filtering and deduplication by `(source_path, chunk_index)`. `query_index_multi` fans out multiple queries and merges results.

**edit** — Programmatic config manipulation. `sync_owned_sources` lets ecosystem packages register their sources without overwriting each other. The caller declares which source ids it owns; all others are preserved.

**cli** — Thin CLI layer exposing `init`, `build`, `query`, `status`, and `serve` commands.

## Key design decisions

- **Config-first**: all behavior is driven by YAML. No auto-detection of project structure.
- **Explicit root**: the project root is always passed as an argument, never inferred.
- **Standalone**: indexio has no knowledge of projio, codio, biblio, or notio. It just indexes files and answers queries.
- **Lazy imports**: heavy dependencies (langchain, chromadb, huggingface) are imported inside functions to keep import time fast.
