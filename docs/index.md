# indexio

Lightweight semantic indexing and retrieval for project knowledge sources.

Indexes document sources (markdown, code, YAML, etc.) into a ChromaDB vector store and provides semantic search. Standalone library — no knowledge of projio or other ecosystem packages.

---

## Current status

**Version:** 0.1.0 (scaffolded, not yet published to PyPI)

### What works

- **Config system** — YAML-based config (`IndexioConfig`) with explicit `root` argument, no auto-detection. Supports `includes:` for config composition and multiple named stores.
- **Build pipeline** — `build_index()` reads source globs or paths, splits documents with `RecursiveCharacterTextSplitter`, batches embeddings via HuggingFace, upserts into Chroma. Full rebuild (clears store) and partial rebuild (by source id) both supported.
- **Query** — `query_index()` and `query_index_multi()` with optional corpus filter, deduplication by source path + chunk index.
- **Edit helpers** — `sync_owned_sources()` / `replace_owned_sources()` for programmatic YAML config management (used by other ecosystem tools that register their own sources).
- **CLI** — `indexio init-config / build / query / status / serve` with `--root`, `--store`, `--sources`, `--corpus`, `--k`, `--json` flags.
- **Chat server** — `indexio.chat` subpackage providing a unified RAG chatbot for all projio subsystems. FastAPI backend with `/chat/` endpoint, pluggable LLM backends (Ollama, OpenAI-compatible), and a reusable JS/CSS frontend widget. Install with `pip install indexio[chat]`, run with `indexio serve`.
- **Package structure** — `src/` layout, `pyproject.toml`, `Makefile` following biblio/notio conventions.

### What is not yet done

- No tests written yet
- Not published to PyPI
- No docs site (mkdocs not configured)
- Embedding model is hardcoded to `all-MiniLM-L6-v2`; no pluggable embedding backend yet
- No incremental/delta indexing (modified-file detection)
- No support for binary or PDF sources

---

## Future plan

### Near-term (v0.1.x)

- [ ] Write a test suite (`tests/`) covering config parsing, build pipeline (with a fixture directory), and query round-trip
- [ ] Write tests for the chat pipeline and endpoint
- [ ] Publish to PyPI as `indexio 0.1.0`
- [ ] Set up mkdocs site (material theme) with API reference and usage guide
- [ ] Add `indexio status --json` output for machine consumption
- [ ] Integrate the chatbot widget into biblio, codio, and notio docs sites

### Medium-term (v0.2)

- [ ] **Incremental indexing** — track file mtimes or content hashes in a sidecar JSON; only re-embed changed files on rebuild
- [ ] **PDF/docling source type** — add a `type: pdf` source that runs docling extraction before chunking
- [ ] **Pluggable embeddings** — allow `embedding_backend: openai` or `embedding_backend: ollama` in config, not just HuggingFace
- [ ] **Multi-store query** — `query_index_stores()` that fans out across multiple stores and merges results

### Longer-term (v0.3+)

- [ ] **Watch mode** — `indexio watch --config ...` to re-index on file changes
- [ ] **Export** — dump indexed chunks to JSONL for analysis or migration
- [ ] **Metadata filtering** — richer filter expressions beyond corpus (e.g. by source_id, date range)
- [ ] **Remote stores** — support Chroma HTTP client (not just local persist) as a store backend
