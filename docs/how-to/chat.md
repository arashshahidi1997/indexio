# Run The Chat Server

The chat server provides a RAG-powered Q&A endpoint and an embeddable web widget.

## Install

```bash
pip install indexio[chat]
```

## Start the server

```bash
indexio serve --config infra/indexio/config.yaml --root .
```

## Custom LLM backend

```bash
# OpenAI-compatible API
indexio serve --config infra/indexio/config.yaml --root . \
    --llm-backend openai --llm-model gpt-4 \
    --llm-base-url https://api.openai.com

# Local Ollama (default)
indexio serve --config infra/indexio/config.yaml --root . \
    --llm-backend ollama --llm-model llama3
```

## Environment variables

All settings can be overridden via `INDEXIO_CHAT_*` environment variables:

```bash
INDEXIO_CHAT_PORT=8080
INDEXIO_CHAT_LLM_MODEL=mistral
```

## Embed the widget

```html
<script>
  window.INDEXIO_CHAT = {
    apiUrl: "http://localhost:9100/chat/",
    title: "My Docs Assistant",
  };
</script>
<script src="http://localhost:9100/chatbot/chatbot.js"></script>
<link href="http://localhost:9100/chatbot/chatbot.css" rel="stylesheet">
```
