# indexio

Lightweight semantic indexing and retrieval for project knowledge sources.

## Quick Reference

- **Language:** Python 3.11+
- **Package layout:** `src/indexio/` (setuptools with `src` layout)
- **Entry point:** `indexio.cli:main`
- **Version:** 0.1.0 (pre-release, not yet on PyPI)

## Build & Test

```bash
make dev            # install editable with dev extras
make test           # pytest (PYTHONPATH=src)
make build          # wheel + sdist
make check          # twine check
make clean          # remove build artifacts
```

Custom Python/tool paths are set in the Makefile header — do not change them.

## Save & Publish (DataLad)

```bash
make save MSG="…"   # datalad save
make push           # datalad push --to github
make publish        # PyPI via personal helper
make publish-test   # TestPyPI
```

## Architecture

- `config.py` — YAML config loading, schema, composition via `includes:`
- `build.py` — indexing pipeline: load → chunk → embed → upsert to ChromaDB
- `chunkers.py` — pluggable chunking backends (text, ast, code/tree-sitter)
- `graph.py` — code structure graph for graph-RAG (symbols, calls, imports)
- `query.py` — vector similarity search with corpus/symbol_type filtering & dedup
- `edit.py` — programmatic config manipulation (source registration)
- `cli.py` — CLI: `init`, `build`, `query`, `status`
- `chat/` — FastAPI RAG server with pluggable LLM backends (Ollama, OpenAI-compatible)

## Chunking Backends

Sources can specify a `chunker` field in config to select a chunking strategy:

- `text` (default) — `RecursiveCharacterTextSplitter`, character-based splitting
- `ast` — Python stdlib `ast` module, splits by function/class (zero extra deps)
- `code` — tree-sitter structural chunking, multi-language (requires `pip install indexio[code]`)

```yaml
sources:
  - id: docs
    corpus: docs
    glob: "docs/**/*.md"
    # chunker defaults to "text"

  - id: code
    corpus: code
    glob: "src/**/*.py"
    chunker: ast
    chunker_options:
      max_chunk_chars: 3000
```

Code-aware chunkers add metadata: `symbol_name`, `symbol_type`, `language`, `start_line`, `end_line`.

## Graph-RAG

`graph.py` builds an in-memory code structure graph from Python AST:

- **Nodes**: modules, functions, classes, methods (with docstrings)
- **Edges**: contains, calls, imports, inherits
- **Features**: subgraph extraction, cross-file call resolution, graph-augmented retrieval
- **API**: `build_file_graph()`, `build_project_graph()`, `expand_results_with_graph()`

## Conventions

- Config is YAML-driven; explicit `root` argument (no auto-detection)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- Chunking: pluggable via `chunker` field; default is `RecursiveCharacterTextSplitter`
- Vector store: ChromaDB (embedded or HTTP)
- Dependencies are minimal by design — avoid adding heavy frameworks
- tree-sitter is an optional dependency (`[code]` extras group)
