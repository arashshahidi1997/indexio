"""RAG pipeline: retrieve context from indexio, generate answer via LLM."""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any

from .models import SourceRef

logger = logging.getLogger("indexio.chat")

# ── Prompt template ──────────────────────────────────────────────

SYSTEM_PROMPT = """\
You are a helpful documentation assistant. Answer the user's question using \
ONLY the context provided below. If the context does not contain enough \
information, say so honestly. Cite the source when possible.

Context:
{context}
"""


# ── LLM backends ────────────────────────────────────────────────

def _call_ollama(prompt: str, *, model: str, base_url: str) -> str:
    """Call a local Ollama instance."""
    url = f"{base_url}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data.get("response", "")


def _call_openai_compat(
    prompt: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    system: str,
) -> str:
    """Call any OpenAI-compatible API (OpenAI, vLLM, LM Studio, etc.)."""
    url = f"{base_url}/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read())
    return data["choices"][0]["message"]["content"]


# ── Retrieval ────────────────────────────────────────────────────

def _retrieve(
    query: str,
    *,
    config_path: str | Path,
    root: str | Path,
    store: str | None,
    corpus: str | None,
    k: int,
) -> list[dict[str, Any]]:
    """Retrieve relevant chunks from the indexio vector store."""
    from indexio.query import query_index

    payload = query_index(
        config_path=config_path,
        root=root,
        query=query,
        store=store,
        prefer_canonical=True,
        corpus=corpus,
        k=k,
    )
    return payload.get("results", [])


def _format_context(results: list[dict[str, Any]]) -> str:
    """Format retrieved chunks into a context string for the LLM."""
    parts: list[str] = []
    for i, r in enumerate(results, 1):
        source = r.get("source_path") or r.get("source_id") or "unknown"
        snippet = r.get("snippet", "")
        parts.append(f"[{i}] ({source})\n{snippet}")
    return "\n\n".join(parts)


def _results_to_sources(results: list[dict[str, Any]]) -> list[SourceRef]:
    """Convert raw query results to SourceRef models."""
    return [
        SourceRef(
            source_id=r.get("source_id"),
            corpus=r.get("corpus"),
            source_path=r.get("source_path"),
            chunk_index=r.get("chunk_index"),
            snippet=r.get("snippet"),
        )
        for r in results
    ]


# ── Public API ───────────────────────────────────────────────────

def rag_pipeline(
    message: str,
    *,
    config_path: str | Path,
    root: str | Path,
    store: str | None = None,
    corpus: str | None = None,
    k: int = 6,
    llm_backend: str = "ollama",
    llm_model: str = "llama3",
    llm_base_url: str = "http://localhost:11434",
    llm_api_key: str = "",
) -> tuple[str, list[SourceRef]]:
    """Run the full RAG pipeline: retrieve context, then generate an answer.

    Args:
        message: The user's question.
        config_path: Path to the indexio YAML config.
        root: Project root for resolving relative paths.
        store: Named store from the config (optional).
        corpus: Optional corpus filter for retrieval.
        k: Number of chunks to retrieve.
        llm_backend: "ollama" or "openai" (any OpenAI-compatible API).
        llm_model: Model name to use.
        llm_base_url: Base URL for the LLM API.
        llm_api_key: API key (required for openai backend).

    Returns:
        (answer, sources) tuple.
    """
    # 1. Retrieve
    results = _retrieve(
        message,
        config_path=config_path,
        root=root,
        store=store,
        corpus=corpus,
        k=k,
    )
    sources = _results_to_sources(results)

    if not results:
        return "I couldn't find any relevant information in the knowledge base.", sources

    # 2. Build prompt
    context = _format_context(results)
    system = SYSTEM_PROMPT.format(context=context)
    user_prompt = message

    # 3. Generate
    try:
        if llm_backend == "ollama":
            answer = _call_ollama(
                f"{system}\n\nQuestion: {user_prompt}",
                model=llm_model,
                base_url=llm_base_url,
            )
        elif llm_backend == "openai":
            answer = _call_openai_compat(
                user_prompt,
                model=llm_model,
                base_url=llm_base_url,
                api_key=llm_api_key,
                system=system,
            )
        else:
            raise ValueError(f"Unknown LLM backend: {llm_backend!r}")
    except Exception as exc:
        logger.error("LLM call failed: %s", exc)
        answer = (
            "I found relevant documents but could not generate an answer "
            f"(LLM error: {exc}). Here are the sources I found."
        )

    return answer, sources
