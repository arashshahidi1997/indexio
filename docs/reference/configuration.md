# Configuration Reference

indexio uses a YAML config file. The default location is `.indexio/config.yaml`.

## Full schema

```yaml
# Optional: compose from other configs
includes:
  - path/to/base.yaml

# Embedding model (HuggingFace model name)
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"

# Chunking parameters
chunk_size_chars: 1000
chunk_overlap_chars: 200

# Store selection
default_store: local
canonical_store: shared    # optional, preferred for reads if it exists

# Named stores
stores:
  local:
    persist_directory: .cache/indexio/chroma_db
    read_only: false
    description: "Per-clone writable Chroma cache"
  shared:
    persist_directory: /data/shared/chroma_db
    read_only: true
    description: "Read-only canonical store"

# Document sources
sources:
  - id: docs
    corpus: docs
    glob: "docs/**/*.md"
    exclude:
      - "docs/drafts/**"

  - id: readme
    corpus: docs
    path: README.md
```

## Top-level keys

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `includes` | list[str] | `[]` | Paths to other YAML configs to merge (relative to this file) |
| `embedding_model` | str | `sentence-transformers/all-MiniLM-L6-v2` | HuggingFace model name |
| `chunk_size_chars` | int | `1000` | Max chunk size in characters |
| `chunk_overlap_chars` | int | `200` | Overlap between adjacent chunks |
| `default_store` | str | first store | Store used by default |
| `canonical_store` | str | none | Preferred store for reads (if it exists on disk) |

## Store definition

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `persist_directory` | str | yes | Path to ChromaDB directory (relative to project root) |
| `read_only` | bool | no | If true, `build` refuses to write to this store |
| `description` | str | no | Human-readable label |

## Source definition

Each source must define exactly one of `path` or `glob`.

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `id` | str | yes | Unique identifier for this source |
| `corpus` | str | yes | Corpus tag stored in chunk metadata |
| `glob` | str | one of | Glob pattern relative to project root |
| `path` | str | one of | Single file path relative to project root |
| `exclude` | list[str] | no | Glob patterns to exclude (applied to relative paths) |
| `chunker` | str | no | Chunking backend: `text` (default), `ast`, or `code` |
| `chunker_options` | dict | no | Backend-specific options (see below) |

### Chunker backends

**`text`** (default) — Character-based `RecursiveCharacterTextSplitter`. Uses `chunk_size_chars` and `chunk_overlap_chars` from the top-level config.

**`ast`** — Python stdlib `ast` module. Splits Python files by function/class. Falls back to `text` for non-Python files or on parse errors. Zero extra dependencies.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `include_docstrings` | bool | `true` | Include docstrings in chunks |
| `max_chunk_chars` | int | `3000` | Symbols larger than this are sub-split with text chunker |

**`code`** — Tree-sitter structural chunking. Supports Python, JavaScript, TypeScript, Go, Rust, Java, C/C++, Ruby. Requires `pip install indexio[code]`. Falls back to `ast` (Python) or `text` (other languages) when tree-sitter is not installed.

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `max_chunk_chars` | int | `3000` | Symbols larger than this are sub-split |
| `languages` | list[str] | all | Restrict to specific languages |

Code-aware chunkers enrich chunk metadata with: `symbol_name`, `symbol_type` (function/class/method/module), `language`, `start_line`, `end_line`.

Example:

```yaml
sources:
  - id: code
    corpus: code
    glob: "src/**/*.py"
    chunker: ast
    chunker_options:
      max_chunk_chars: 5000
```

## Config composition

Use `includes` to merge configs from multiple ecosystem packages:

```yaml
includes:
  - bib/config/indexio.yaml
  - .codio/indexio.yaml

stores:
  local:
    persist_directory: .cache/indexio/chroma_db
```

Merge rules:

- **stores**: merged by name (overlay wins on conflict)
- **sources**: merged by `id` (overlay wins on conflict, new ids appended)
- **scalars**: overlay replaces base
- **`includes`** key itself is never propagated into the merged result
