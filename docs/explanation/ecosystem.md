# Role In The Projio Ecosystem

indexio provides the shared retrieval layer for the projio ecosystem.

## The pattern

Each ecosystem package owns its content and registers sources into a shared indexio config:

- **codio** registers `.codio/**/*.md` and `catalog.yml` → corpus `codelib`
- **biblio** registers `bib/derivatives/docling/**/*.md` → corpus `biblio_docling`
- **notio** notes are indexed → corpus `notes`

indexio does not know what the content means. It chunks, embeds, and searches.

## Why a shared layer

If each package managed its own RAG:

- Duplicate infrastructure (three copies of ChromaDB, embedding models, chunking logic)
- No cross-corpus search (an agent asking "what do we know about X?" would need three separate calls)
- Inconsistent embeddings across corpora make similarity scores incomparable
- Resource waste from multiple embedding models loaded in memory

## The contract

```
codio, biblio, notio  →  content owners (know WHAT to index)
indexio               →  retrieval engine (knows HOW to index)
projio MCP server     →  query surface (knows WHO is asking)
```

Each package has a `rag sync` command that calls `sync_owned_sources`. This is the entire integration surface. indexio never imports ecosystem packages; they never import indexio at build time.

## Source registration flow

1. Package calls `sync_owned_sources(config_path, root, owned_source_ids=[...], sources=[...])`
2. indexio reads the config, replaces only the caller's sources, preserves everything else
3. On `indexio build`, all registered sources are indexed into a single ChromaDB store
4. On `indexio query`, results from all corpora are returned (optionally filtered by corpus)
