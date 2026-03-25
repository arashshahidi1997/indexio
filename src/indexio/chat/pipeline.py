"""RAG pipeline: retrieve context from indexio, generate answer via LLM."""

from __future__ import annotations

import json
import logging
import urllib.request
from pathlib import Path
from typing import Any, Iterator

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


# ── LLM backends (non-streaming) ────────────────────────────────

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


# ── LLM backends (streaming) ────────────────────────────────────

def _stream_ollama(prompt: str, *, model: str, base_url: str) -> Iterator[str]:
    """Stream tokens from a local Ollama instance."""
    url = f"{base_url}/api/generate"
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": True,
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        for line in resp:
            if not line.strip():
                continue
            chunk = json.loads(line)
            token = chunk.get("response", "")
            if token:
                yield token
            if chunk.get("done"):
                break


def _stream_openai_compat(
    prompt: str,
    *,
    model: str,
    base_url: str,
    api_key: str,
    system: str,
) -> Iterator[str]:
    """Stream tokens from any OpenAI-compatible API."""
    url = f"{base_url}/v1/chat/completions"
    payload = json.dumps({
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "stream": True,
    }).encode()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(url, data=payload, headers=headers)
    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8").strip()
            if not line or not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                break
            chunk = json.loads(data_str)
            delta = chunk.get("choices", [{}])[0].get("delta", {})
            token = delta.get("content", "")
            if token:
                yield token


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


def _source_path_to_url(source_path: str | None, site_url: str | None) -> str | None:
    """Convert a docs source path to a clickable site URL.

    Handles the common MkDocs convention: ``docs/foo/bar.md`` → ``foo/bar/``.
    """
    if not source_path or not site_url:
        return None
    from pathlib import PurePosixPath

    p = PurePosixPath(source_path)
    # Strip leading docs directory (e.g. "docs/ref/tools.md" → "ref/tools.md")
    if p.parts and p.parts[0] == "docs":
        p = PurePosixPath(*p.parts[1:])
    # Convert .md to trailing slash (MkDocs URL style)
    if p.suffix == ".md":
        if p.stem == "index":
            slug = str(p.parent)
        else:
            slug = str(p.with_suffix(""))
    else:
        slug = str(p)
    base = site_url.rstrip("/")
    slug = slug.strip(".")
    return f"{base}/{slug}/" if slug else f"{base}/"


def _results_to_sources(results: list[dict[str, Any]], *, site_url: str | None = None) -> list[SourceRef]:
    """Convert raw query results to SourceRef models."""
    return [
        SourceRef(
            source_id=r.get("source_id"),
            corpus=r.get("corpus"),
            source_path=r.get("source_path"),
            chunk_index=r.get("chunk_index"),
            snippet=r.get("snippet"),
            url=_source_path_to_url(r.get("source_path"), site_url),
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
    site_url: str | None = None,
    use_llm: bool = True,
) -> tuple[str, list[SourceRef]]:
    """Run the full RAG pipeline: retrieve context, then generate an answer.

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
    sources = _results_to_sources(results, site_url=site_url)

    if not results:
        return "I couldn't find any relevant information in the knowledge base.", sources

    if not use_llm:
        return "Here are the most relevant sources I found.", sources

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


def rag_pipeline_stream(
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
    site_url: str | None = None,
    use_llm: bool = True,
) -> Iterator[dict[str, Any]]:
    """Streaming RAG pipeline.  Yields SSE-ready event dicts:

    - ``{"event": "phase", "data": "searching"}``
    - ``{"event": "sources", "data": [<SourceRef dicts>]}``
    - ``{"event": "phase", "data": "generating"}``
    - ``{"event": "token", "data": "<text>"}``  (repeated)
    - ``{"event": "done", "data": ""}``
    - ``{"event": "error", "data": "<message>"}``  (on LLM failure)
    """
    # 1. Retrieve
    yield {"event": "phase", "data": "searching"}
    results = _retrieve(
        message,
        config_path=config_path,
        root=root,
        store=store,
        corpus=corpus,
        k=k,
    )
    sources = _results_to_sources(results, site_url=site_url)

    # 2. Send sources immediately
    yield {"event": "sources", "data": [s.model_dump() for s in sources]}

    if not results:
        yield {"event": "token", "data": "I couldn't find any relevant information in the knowledge base."}
        yield {"event": "done", "data": ""}
        return

    if not use_llm:
        yield {"event": "token", "data": "Here are the most relevant sources I found."}
        yield {"event": "done", "data": ""}
        return

    # 3. Stream LLM
    yield {"event": "phase", "data": "generating"}
    context = _format_context(results)
    system = SYSTEM_PROMPT.format(context=context)
    user_prompt = message

    try:
        if llm_backend == "ollama":
            for token in _stream_ollama(
                f"{system}\n\nQuestion: {user_prompt}",
                model=llm_model,
                base_url=llm_base_url,
            ):
                yield {"event": "token", "data": token}
        elif llm_backend == "openai":
            for token in _stream_openai_compat(
                user_prompt,
                model=llm_model,
                base_url=llm_base_url,
                api_key=llm_api_key,
                system=system,
            ):
                yield {"event": "token", "data": token}
        else:
            raise ValueError(f"Unknown LLM backend: {llm_backend!r}")
    except Exception as exc:
        logger.error("LLM stream failed: %s", exc)
        yield {"event": "error", "data": str(exc)}

    yield {"event": "done", "data": ""}
