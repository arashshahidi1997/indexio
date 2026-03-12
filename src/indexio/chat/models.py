"""Pydantic models for the chat API."""

from __future__ import annotations

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Incoming chat message."""

    message: str


class SourceRef(BaseModel):
    """A single source reference returned alongside an answer."""

    source_id: str | None = None
    corpus: str | None = None
    source_path: str | None = None
    chunk_index: int | None = None
    snippet: str | None = None


class ChatResponse(BaseModel):
    """Chat answer with optional source references."""

    answer: str
    sources: list[SourceRef] = []
