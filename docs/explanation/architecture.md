# Architecture

indexio is a lightweight semantic indexing and retrieval library organized into seven modules.

## Pipeline

```
YAML Config → Load Sources → Read Files → Chunk (text/ast/code) → Embed → Upsert to ChromaDB
                                                      ↓
                                              Code Graph (optional)
                                                      ↓
                                          Graph-Augmented Retrieval
```

## Modules

**config** — Loads and validates YAML configuration. Supports composition via `includes:` for merging configs from multiple ecosystem packages. Resolves stores and sources into typed dataclasses.

**build** — Reads files matched by source globs or paths, dispatches to the configured chunker backend, generates embeddings via HuggingFace, and upserts into ChromaDB in batches of 100. Supports full rebuild (clear + reindex) and partial rebuild (by source id).

**chunkers** — Pluggable chunking backends. Three backends available:

- `text` — default character-based `RecursiveCharacterTextSplitter`
- `ast` — Python stdlib `ast`, splits by function/class (zero extra deps)
- `code` — tree-sitter structural chunking for multi-language support (optional dep)

Code-aware chunkers enrich metadata with symbol names, types, line ranges, and language.

**graph** — Code structure graph for graph-RAG. Builds an in-memory graph of symbols and their relationships (calls, imports, containment, inheritance) using Python's `ast` module. Supports cross-file call resolution, subgraph extraction, and graph-augmented retrieval that expands vector search results with structurally related symbols.

**query** — Wraps ChromaDB similarity search with optional corpus and symbol_type filtering, plus deduplication by `(source_path, chunk_index)`. `query_index_multi` fans out multiple queries and merges results.

**edit** — Programmatic config manipulation. `sync_owned_sources` lets ecosystem packages register their sources without overwriting each other. The caller declares which source ids it owns; all others are preserved.

**cli** — Thin CLI layer exposing `init`, `build`, `query`, `status`, and `serve` commands.

## Key design decisions

- **Config-first**: all behavior is driven by YAML. No auto-detection of project structure.
- **Explicit root**: the project root is always passed as an argument, never inferred.
- **Standalone**: indexio has no knowledge of projio, codio, biblio, or notio. It just indexes files and answers queries.
- **Lazy imports**: heavy dependencies (langchain, chromadb, huggingface, tree-sitter) are imported inside functions to keep import time fast.
- **Graceful fallback**: code chunkers fall back to simpler backends when optional deps are missing (code → ast → text).
