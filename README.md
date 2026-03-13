# indexio

Lightweight semantic indexing and retrieval for project knowledge sources for prompt and context engineering.

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
indexio init

# Build the index
indexio build

# Query
indexio query "how does authentication work"

# Show store status
indexio status
```

`indexio status` compares the current source matches to the last build manifest and groups sources into buckets such as `indexed`, `changed`, and `not yet built`.

## Chat server

A built-in RAG chatbot backend and embeddable widget.

`indexio` owns the chat API, demo page, and widget assets.
`projio` owns site-builder-specific mounting for ecosystem docs sites.

```bash
# Install with chat support
pip install indexio[chat]

# Start the chat server
indexio serve

# With a custom LLM
indexio serve \
    --llm-backend openai --llm-model gpt-4 --llm-base-url https://api.openai.com
```

Open the URL printed by the server, such as `http://localhost:9100/`.
If that port is already in use, `indexio serve` will automatically pick the next free port and print it.

Embed the widget directly in any docs site:

```html
<script>
  window.INDEXIO_CHAT = {
    apiUrl: "http://localhost:9100/chat/",
    title: "My Docs Assistant",
    storageKey: "myproject_chat_v1",
  };
</script>
<script src="http://localhost:9100/chatbot/chatbot.js"></script>
<link href="http://localhost:9100/chatbot/chatbot.css" rel="stylesheet">
```

Settings are also configurable via `INDEXIO_CHAT_*` environment variables.

If your project uses `projio` to build docs sites, prefer enabling chatbot injection there instead of wiring the widget tags by hand.

## Python API

```python
from indexio import load_indexio_config, build_index, query_index

cfg = load_indexio_config(".indexio/config.yaml", root="/path/to/project")
build_index(config_path=".indexio/config.yaml", root="/path/to/project")
results = query_index(config_path=".indexio/config.yaml", root="/path/to/project", query="embeddings")
```
