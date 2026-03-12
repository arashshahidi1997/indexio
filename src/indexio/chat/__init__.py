"""indexio.chat — unified chatbot backend for projio subsystems."""

from .models import ChatRequest, ChatResponse
from .pipeline import rag_pipeline

__all__ = [
    "ChatRequest",
    "ChatResponse",
    "rag_pipeline",
]
