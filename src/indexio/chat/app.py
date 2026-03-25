"""FastAPI application for the indexio chat server."""

from __future__ import annotations

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import StreamingResponse

from .models import ChatRequest, ChatResponse, SourceRef
from .pipeline import rag_pipeline, rag_pipeline_stream
from .settings import ChatSettings, get_settings

STATIC_DIR = Path(__file__).parent / "static"


def _chatbot_page(settings: ChatSettings) -> str:
    title = settings.title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
      :root {{
        color-scheme: light;
        font-family: ui-sans-serif, system-ui, sans-serif;
      }}
      body {{
        margin: 0;
        min-height: 100vh;
        display: grid;
        place-items: center;
        background:
          radial-gradient(circle at top, #f0f7ff, #ffffff 45%),
          linear-gradient(135deg, #fafafa, #eef5ff);
        color: #10233f;
      }}
      main {{
        width: min(720px, calc(100vw - 32px));
        padding: 32px;
        border-radius: 20px;
        background: rgba(255, 255, 255, 0.9);
        box-shadow: 0 16px 48px rgba(16, 35, 63, 0.12);
      }}
      h1 {{
        margin: 0 0 12px;
        font-size: clamp(2rem, 5vw, 3rem);
      }}
      p {{
        margin: 0 0 12px;
        line-height: 1.6;
      }}
      code {{
        padding: 0.15rem 0.4rem;
        border-radius: 6px;
        background: #eef4ff;
      }}
    </style>
    <script>
      window.INDEXIO_CHAT = {{
        apiUrl: "/chat/",
        streamUrl: "/chat/stream",
        statusUrl: "/status",
        title: "{title}",
      }};
    </script>
    <script src="/chatbot/chatbot.js" defer></script>
    <link href="/chatbot/chatbot.css" rel="stylesheet">
  </head>
  <body>
    <main>
      <h1>{title}</h1>
      <p>The chat server is running.</p>
      <p>Use the floating widget in the lower corner or send requests to <code>/chat/</code>.</p>
      <p>Health check: <code>/health</code></p>
    </main>
  </body>
</html>
"""


# Vector store status: "loading" → "ready" | "error"
_vs_status: dict[str, str] = {"state": "loading", "detail": ""}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Warm up the vector store on startup."""
    settings: ChatSettings = app.state.settings
    loop = asyncio.get_running_loop()

    print("[indexio-chat] Warming up vector store ...")
    try:
        from indexio.query import get_vectorstore

        await loop.run_in_executor(
            None,
            lambda: get_vectorstore(
                config_path=settings.config_path,
                root=settings.root,
                store=settings.store,
                prefer_canonical=True,
            ),
        )
        _vs_status["state"] = "ready"
        _vs_status["detail"] = ""
        print("[indexio-chat] Vector store ready.")
    except Exception as exc:
        _vs_status["state"] = "error"
        _vs_status["detail"] = str(exc)
        print(f"[indexio-chat] WARNING: warmup failed: {exc}")

    yield
    print("[indexio-chat] Shutting down.")


def create_app(settings: ChatSettings | None = None) -> FastAPI:
    """Create and configure the FastAPI application."""
    if settings is None:
        settings = get_settings()

    app = FastAPI(
        title="indexio chat",
        description="Unified RAG chatbot for projio subsystems.",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Routes ───────────────────────────────────────────────────

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/status")
    async def status():
        return {"vectorstore": _vs_status["state"], "detail": _vs_status["detail"]}

    @app.get("/", response_class=HTMLResponse)
    async def index():
        return HTMLResponse(_chatbot_page(settings))

    @app.post("/chat/", response_model=ChatResponse)
    async def chat(body: ChatRequest):
        """Generate an answer using the RAG pipeline."""
        loop = asyncio.get_running_loop()
        answer, sources = await loop.run_in_executor(
            None,
            lambda: rag_pipeline(
                body.message,
                config_path=settings.config_path,
                root=settings.root,
                store=settings.store,
                corpus=settings.corpus,
                k=body.k if body.k is not None else settings.k,
                llm_backend=settings.llm_backend,
                llm_model=settings.llm_model,
                llm_base_url=settings.llm_base_url,
                llm_api_key=settings.llm_api_key,
                site_url=settings.site_url,
                use_llm=body.use_llm,
            ),
        )
        return ChatResponse(answer=answer, sources=sources)

    @app.post("/chat/stream")
    async def chat_stream(body: ChatRequest):
        """SSE streaming endpoint: sources first, then LLM tokens."""
        loop = asyncio.get_running_loop()

        async def event_generator():
            gen = rag_pipeline_stream(
                body.message,
                config_path=settings.config_path,
                root=settings.root,
                store=settings.store,
                corpus=settings.corpus,
                k=body.k if body.k is not None else settings.k,
                llm_backend=settings.llm_backend,
                llm_model=settings.llm_model,
                llm_base_url=settings.llm_base_url,
                llm_api_key=settings.llm_api_key,
                site_url=settings.site_url,
                use_llm=body.use_llm,
            )
            # Pull events from the synchronous generator in a thread
            while True:
                try:
                    evt = await loop.run_in_executor(None, next, gen)
                except StopIteration:
                    break
                line = f"event: {evt['event']}\ndata: {json.dumps(evt['data'])}\n\n"
                yield line

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    # ── Serve the chatbot widget static files ────────────────────

    if STATIC_DIR.is_dir():
        app.mount(
            "/chatbot",
            StaticFiles(directory=str(STATIC_DIR)),
            name="chatbot-static",
        )

    return app
