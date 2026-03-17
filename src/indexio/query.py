from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import load_indexio_config, resolve_store


def make_embeddings(model_name: str):
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=model_name)


def get_vectorstore(
    *,
    config_path: str | Path,
    root: str | Path,
    store: str | None = None,
    prefer_canonical: bool = False,
):
    from langchain_chroma import Chroma

    config = load_indexio_config(config_path, root=root)
    store_cfg = resolve_store(
        config,
        store=store,
        prefer_canonical=prefer_canonical,
        must_exist=True,
    )
    embeddings = make_embeddings(config.embedding_model)
    db = Chroma(
        embedding_function=embeddings,
        persist_directory=str(store_cfg.persist_directory),
    )
    return config, store_cfg, db


def _doc_to_result(doc: Any) -> dict[str, Any]:
    meta = doc.metadata or {}
    snippet = doc.page_content.strip().replace("\n", " ")
    result: dict[str, Any] = {
        "corpus": meta.get("corpus"),
        "source_id": meta.get("source_id"),
        "source_path": meta.get("source_path"),
        "chunk_index": meta.get("chunk_index"),
        "snippet": snippet[:400],
    }
    # Include code-aware metadata when present
    for key in (
        "symbol_name", "symbol_type", "language", "start_line", "end_line",
    ):
        if key in meta:
            result[key] = meta[key]
    return result


def _build_filter(
    corpus: str | None = None,
    symbol_type: str | None = None,
) -> dict[str, Any] | None:
    """Build a ChromaDB where-filter from optional constraints."""
    conditions: list[dict[str, Any]] = []
    if corpus:
        conditions.append({"corpus": corpus})
    if symbol_type:
        conditions.append({"symbol_type": symbol_type})
    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


def query_index(
    *,
    config_path: str | Path,
    root: str | Path,
    query: str,
    store: str | None = None,
    prefer_canonical: bool = False,
    corpus: str | None = None,
    symbol_type: str | None = None,
    k: int = 4,
) -> dict[str, Any]:
    config, store_cfg, db = get_vectorstore(
        config_path=config_path,
        root=root,
        store=store,
        prefer_canonical=prefer_canonical,
    )
    where = _build_filter(corpus=corpus, symbol_type=symbol_type)
    if where:
        docs = db.similarity_search(query, k=k, filter=where)
    else:
        docs = db.similarity_search(query, k=k)
    return {
        "query": query,
        "config_path": str(config.config_path),
        "store": store_cfg.name,
        "persist_directory": str(store_cfg.persist_directory),
        "corpus": corpus,
        "symbol_type": symbol_type,
        "k": k,
        "results": [_doc_to_result(doc) for doc in docs],
    }


def query_index_multi(
    *,
    config_path: str | Path,
    root: str | Path,
    queries: list[str],
    store: str | None = None,
    prefer_canonical: bool = False,
    corpus: str | None = None,
    symbol_type: str | None = None,
    k: int = 4,
) -> dict[str, Any]:
    seen: set[tuple[Any, Any]] = set()
    merged: list[dict[str, Any]] = []
    last_meta: dict[str, Any] | None = None
    for query in queries:
        payload = query_index(
            config_path=config_path,
            root=root,
            query=query,
            store=store,
            prefer_canonical=prefer_canonical,
            corpus=corpus,
            symbol_type=symbol_type,
            k=k,
        )
        last_meta = payload
        for result in payload["results"]:
            key = (result.get("source_path"), result.get("chunk_index"))
            if key in seen:
                continue
            seen.add(key)
            merged.append(result)
    return {
        "queries": queries,
        "config_path": (
            None if last_meta is None else last_meta["config_path"]
        ),
        "store": (
            None if last_meta is None else last_meta["store"]
        ),
        "persist_directory": (
            None if last_meta is None else last_meta["persist_directory"]
        ),
        "corpus": corpus,
        "symbol_type": symbol_type,
        "k": k,
        "results": merged,
    }