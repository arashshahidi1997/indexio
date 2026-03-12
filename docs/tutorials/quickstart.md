# Quickstart

This tutorial walks you through indexing a set of markdown files and running your first semantic query.

## Prerequisites

```bash
pip install indexio
```

## 1. Initialize a config

```bash
indexio init-config --root .
```

This writes a starter config to `.indexio/config.yaml` with a `docs/**/*.md` source and a local ChromaDB store.

## 2. Build the index

```bash
indexio build --config .indexio/config.yaml --root .
```

indexio reads every file matched by your source globs, splits them into chunks, generates embeddings, and stores them in ChromaDB.

## 3. Query

```bash
indexio query --config .indexio/config.yaml --root . "how does authentication work"
```

Results show the most semantically similar chunks, with corpus, source path, and a snippet.

## 4. Check status

```bash
indexio status --config .indexio/config.yaml --root .
```

Lists configured stores (with existence checks) and registered sources.

## Next steps

- [Register sources from other packages](../how-to/register-sources.md)
- [Run the chat server](../how-to/chat.md)
- [Configuration reference](../reference/configuration.md)
