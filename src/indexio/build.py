from __future__ import annotations

import gc
import time
from pathlib import Path
from typing import Any

from .config import IndexioConfig, SourceConfig, load_indexio_config, resolve_store

BATCH_SIZE = 100


def make_embeddings(model_name: str):
    from langchain_huggingface import HuggingFaceEmbeddings

    return HuggingFaceEmbeddings(model_name=model_name)


def _split_docs(docs: list, chunk_size: int, chunk_overlap: int) -> list:
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    return splitter.split_documents(docs)


def _source_paths(config: IndexioConfig, src: SourceConfig) -> list[Path]:
    if src.path:
        abs_path = config.root / src.path
        return [abs_path] if abs_path.exists() else []

    assert src.glob is not None
    paths: list[Path] = []
    for path in config.root.glob(src.glob):
        if not path.is_file():
            continue
        rel = path.relative_to(config.root)
        if any(rel.match(pattern) for pattern in src.exclude):
            continue
        paths.append(path)
    return paths


def _make_chunk_ids(chunks: list) -> list[str]:
    ids: list[str] = []
    counters: dict[str, int] = {}
    for chunk in chunks:
        key = f"{chunk.metadata['source_id']}::{chunk.metadata['source_path']}"
        idx = chunk.metadata.get("chunk_index")
        if idx is None:
            idx = counters.get(key, 0)
            counters[key] = idx + 1
        ids.append(f"{key}::{idx}")
    return ids


def _db_upsert(db, *, documents: list, ids: list[str]) -> None:
    texts = [doc.page_content for doc in documents]
    metadatas = [doc.metadata for doc in documents]
    embeddings = db._embedding_function.embed_documents(texts)  # type: ignore[attr-defined]
    db._collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas, documents=texts)


def _build_documents(config: IndexioConfig, src: SourceConfig) -> tuple[list, dict[str, int]]:
    from langchain_core.documents import Document

    docs: list[Document] = []
    n_files = 0
    n_chars = 0
    for path in _source_paths(config, src):
        text = path.read_text(encoding="utf-8", errors="ignore")
        docs.append(
            Document(
                page_content=text,
                metadata={
                    "source_id": src.id,
                    "corpus": src.corpus,
                    "source_path": str(path.relative_to(config.root)),
                },
            )
        )
        n_files += 1
        n_chars += len(text)
    return docs, {"files": n_files, "chars": n_chars}


def _process_source(config: IndexioConfig, src: SourceConfig, *, db, use_upsert: bool = False) -> dict[str, int]:
    stats = {"files": 0, "chars": 0, "chunks": 0}
    t0 = time.perf_counter()
    docs, base_stats = _build_documents(config, src)
    t1 = time.perf_counter()
    stats.update(base_stats)

    chunks = _split_docs(docs, config.chunk_size_chars, config.chunk_overlap_chars)
    t2 = time.perf_counter()
    counters: dict[str, int] = {}
    for chunk in chunks:
        key = f"{chunk.metadata['source_id']}::{chunk.metadata['source_path']}"
        idx = counters.get(key, 0)
        chunk.metadata["chunk_index"] = idx
        counters[key] = idx + 1
    stats["chunks"] = len(chunks)

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        if use_upsert:
            _db_upsert(db, documents=batch, ids=_make_chunk_ids(batch))
        else:
            db.add_documents(batch)
    t3 = time.perf_counter()

    print(
        f"[TIMER] {src.id}: load={t1 - t0:.1f}s split={t2 - t1:.1f}s embed={t3 - t2:.1f}s"
    )
    del docs
    del chunks
    gc.collect()
    return stats


def build_index(
    *,
    config_path: str | Path,
    root: str | Path,
    store: str | None = None,
    sources_filter: list[str] | None = None,
) -> dict[str, Any]:
    from langchain_chroma import Chroma

    config = load_indexio_config(config_path, root=root)
    store_cfg = resolve_store(config, store=store)
    if store_cfg.read_only:
        raise PermissionError(f"Refusing to build into read-only store '{store_cfg.name}'")

    embeddings = make_embeddings(config.embedding_model)
    persist_directory = store_cfg.persist_directory
    persist_directory.mkdir(parents=True, exist_ok=True)

    db = Chroma(embedding_function=embeddings, persist_directory=str(persist_directory))
    selected_sources = config.sources
    partial = bool(sources_filter)
    if sources_filter:
        wanted = set(sources_filter)
        selected_sources = [src for src in config.sources if src.id in wanted]

    if not partial:
        if persist_directory.exists():
            for path in persist_directory.glob("**/*"):
                if path.is_file():
                    path.unlink()
            for path in sorted(persist_directory.glob("**/*"), reverse=True):
                if path.is_dir():
                    path.rmdir()
            persist_directory.mkdir(parents=True, exist_ok=True)
        db = Chroma(embedding_function=embeddings, persist_directory=str(persist_directory))
    else:
        for src in selected_sources:
            db._collection.delete(where={"source_id": src.id})

    summary: dict[str, dict[str, int]] = {}
    for src in selected_sources:
        summary[src.id] = _process_source(config, src, db=db, use_upsert=partial)

    return {
        "config_path": str(config.config_path),
        "root": str(config.root),
        "store": store_cfg.name,
        "persist_directory": str(store_cfg.persist_directory),
        "partial": partial,
        "source_stats": summary,
    }


def sync_owned_sources(
    config_path: str | Path,
    root: str | Path,
    *,
    owned_source_ids,
    sources,
    force_init: bool = False,
    template: str | None = None,
):
    """Sync owned sources in an indexio config. Delegates to edit.sync_owned_sources."""
    from .edit import sync_owned_sources as _sync
    return _sync(
        config_path,
        root,
        owned_source_ids=owned_source_ids,
        sources=sources,
        force_init=force_init,
        template=template,
    )