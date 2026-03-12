# CLI Reference

## `indexio init`

Write a starter config into a project.

| Flag | Default | Description |
|------|---------|-------------|
| `--root` | `.` | Project root |
| `--output` | `.indexio/config.yaml` | Output path relative to root |
| `--force` | | Overwrite an existing file |

## `indexio build`

Build a Chroma index from an indexio config.

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `.indexio/config.yaml` | Path to the indexio config file |
| `--root` | `.` | Project root |
| `--store` | | Named store from the config |
| `--sources` | | Comma-separated source ids for partial rebuild |
| `--json` | | Print JSON summary |

## `indexio query`

Query the Chroma index.

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `.indexio/config.yaml` | Path to the indexio config file |
| `--root` | `.` | Project root |
| `--store` | | Named store from the config |
| `--corpus` | | Corpus filter |
| `--k` | `8` | Number of results |
| `--json` | | Emit JSON output |
| `query` | *(positional)* | Query text |

## `indexio status`

Show index status for each configured store.

Reports source state without rebuilding by comparing current file matches against the last build manifest stored next to the local index.

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `.indexio/config.yaml` | Path to the indexio config file |
| `--root` | `.` | Project root |

## `indexio serve`

Start the chat server (requires `indexio[chat]`).

| Flag | Default | Description |
|------|---------|-------------|
| `--config` | `.indexio/config.yaml` | Path to the indexio config file |
| `--root` | `.` | Project root |
| `--store` | | Named store |
| `--corpus` | | Corpus filter for retrieval |
| `--host` | `0.0.0.0` | Bind host |
| `--port` | `9100` | Preferred bind port; falls forward to the next free port if occupied |
| `--llm-backend` | `ollama` | LLM backend: `ollama` or `openai` |
| `--llm-model` | `llama3` | LLM model name |
| `--llm-base-url` | `http://localhost:11434` | LLM API base URL |
| `--title` | `Docs Assistant` | Chat widget title |
