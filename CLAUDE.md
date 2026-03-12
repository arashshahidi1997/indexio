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
- `query.py` — vector similarity search with corpus filtering & dedup
- `edit.py` — programmatic config manipulation (source registration)
- `cli.py` — CLI: `init`, `build`, `query`, `status`
- `chat/` — FastAPI RAG server with pluggable LLM backends (Ollama, OpenAI-compatible)

## Conventions

- Config is YAML-driven; explicit `root` argument (no auto-detection)
- Embedding model: `sentence-transformers/all-MiniLM-L6-v2` (384-dim)
- Chunking: `RecursiveCharacterTextSplitter` (default 1000 chars, 200 overlap)
- Vector store: ChromaDB (embedded or HTTP)
- Dependencies are minimal by design — avoid adding heavy frameworks
