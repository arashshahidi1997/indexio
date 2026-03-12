"""FastAPI application for the indexio chat server."""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .models import ChatRequest, ChatResponse, SourceRef
from .pipeline import rag_pipeline
from .settings import ChatSettings, get_settings

STATIC_DIR = Path(__file__).parent / "static"


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
        print("[indexio-chat] Vector store ready.")
    except Exception as exc:
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
                k=settings.k,
                llm_backend=settings.llm_backend,
                llm_model=settings.llm_model,
                llm_base_url=settings.llm_base_url,
                llm_api_key=settings.llm_api_key,
            ),
        )
        return ChatResponse(answer=answer, sources=sources)

    # ── Serve the chatbot widget static files ────────────────────

    if STATIC_DIR.is_dir():
        app.mount(
            "/chatbot",
            StaticFiles(directory=str(STATIC_DIR)),
            name="chatbot-static",
        )

    return app
