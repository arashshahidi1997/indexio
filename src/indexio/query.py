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
    return {
        "corpus": meta.get("corpus"),
        "source_id": meta.get("source_id"),
        "source_path": meta.get("source_path"),
        "chunk_index": meta.get("chunk_index"),
        "snippet": snippet[:400],
    }


def query_index(
    *,
    config_path: str | Path,
    root: str | Path,
    query: str,
    store: str | None = None,
    prefer_canonical: bool = False,
    corpus: str | None = None,
    k: int = 4,
) -> dict[str, Any]:
    config, store_cfg, db = get_vectorstore(
        config_path=config_path,
        root=root,
        store=store,
        prefer_canonical=prefer_canonical,
    )
    if corpus:
        docs = db.similarity_search(query, k=k, filter={"corpus": corpus})
    else:
        docs = db.similarity_search(query, k=k)
    return {
        "query": query,
        "config_path": str(config.config_path),
        "store": store_cfg.name,
        "persist_directory": str(store_cfg.persist_directory),
        "corpus": corpus,
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
        "config_path": None if last_meta is None else last_meta["config_path"],
        "store": None if last_meta is None else last_meta["store"],
        "persist_directory": None if last_meta is None else last_meta["persist_directory"],
        "corpus": corpus,
        "k": k,
        "results": merged,
    }