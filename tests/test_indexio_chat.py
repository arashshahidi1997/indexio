"""Tests for the indexio.chat subpackage: models, pipeline helpers, and app routes."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from indexio.chat.models import ChatRequest, ChatResponse, SourceRef
from indexio.chat.pipeline import _format_context, _results_to_sources, SYSTEM_PROMPT


# ---- models ------------------------------------------------------------------

def test_chat_request_fields() -> None:
    req = ChatRequest(message="hello")
    assert req.message == "hello"


def test_chat_response_defaults() -> None:
    resp = ChatResponse(answer="ok")
    assert resp.answer == "ok"
    assert resp.sources == []


def test_chat_response_with_sources() -> None:
    src = SourceRef(source_id="docs", corpus="docs", source_path="a.md", chunk_index=0)
    resp = ChatResponse(answer="found it", sources=[src])
    assert len(resp.sources) == 1
    assert resp.sources[0].source_id == "docs"


def test_source_ref_optional_fields() -> None:
    src = SourceRef()
    assert src.source_id is None
    assert src.snippet is None


# ---- pipeline helpers --------------------------------------------------------

def test_format_context_empty() -> None:
    assert _format_context([]) == ""


def test_format_context_numbered() -> None:
    results = [
        {"source_path": "a.md", "snippet": "hello"},
        {"source_id": "docs", "snippet": "world"},
    ]
    ctx = _format_context(results)
    assert "[1]" in ctx
    assert "[2]" in ctx
    assert "(a.md)" in ctx
    assert "hello" in ctx


def test_format_context_falls_back_to_source_id() -> None:
    results = [{"source_id": "fallback", "snippet": "text"}]
    ctx = _format_context(results)
    assert "(fallback)" in ctx


def test_results_to_sources_conversion() -> None:
    results = [
        {
            "source_id": "docs",
            "corpus": "docs",
            "source_path": "a.md",
            "chunk_index": 0,
            "snippet": "text",
        }
    ]
    sources = _results_to_sources(results)
    assert len(sources) == 1
    assert isinstance(sources[0], SourceRef)
    assert sources[0].source_id == "docs"
    assert sources[0].chunk_index == 0


def test_system_prompt_has_context_placeholder() -> None:
    assert "{context}" in SYSTEM_PROMPT


# ---- app routes (no LLM / no vector store) -----------------------------------

def test_health_endpoint() -> None:
    from fastapi.testclient import TestClient
    from indexio.chat.app import create_app
    from indexio.chat.settings import ChatSettings

    settings = ChatSettings(config_path="fake.yaml", root="/tmp")
    app = create_app(settings)
    # Skip lifespan warmup by using TestClient without raise_server_exceptions
    client = TestClient(app, raise_server_exceptions=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
