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
