# Run The Chat Server

The chat server provides a RAG-powered Q&A endpoint, a demo page, and embeddable widget assets.

`indexio` is responsible for serving the backend and widget.
If your project uses `projio` for site builds, `projio` is responsible for mounting the widget into supported site frameworks.

## Install

```bash
pip install indexio[chat]
```

## Start the server

```bash
indexio serve
```

Then open the URL printed by the server, such as `http://localhost:9100/`.
If the requested port is already in use, `indexio serve` will automatically pick the next free port and print it.

## Custom LLM backend

```bash
# OpenAI-compatible API
indexio serve \
    --llm-backend openai --llm-model gpt-4 \
    --llm-base-url https://api.openai.com

# Local Ollama (default)
indexio serve \
    --llm-backend ollama --llm-model llama3
```

## Environment variables

All settings can be overridden via `INDEXIO_CHAT_*` environment variables:

```bash
INDEXIO_CHAT_PORT=8080
INDEXIO_CHAT_LLM_MODEL=mistral
```

## Embed the widget directly

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

If you are using `projio`, prefer enabling `site.chatbot` in `.projio/config.yml` so the site builder handles widget injection for you.
