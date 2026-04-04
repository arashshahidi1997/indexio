from __future__ import annotations

import gc
import json
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from .config import IndexioConfig, SourceConfig, load_indexio_config, resolve_store

# Signature: (source_id, source_index, total_sources, source_stats_or_none)
ProgressCallback = Callable[[str, int, int, dict[str, int] | None], None]

BATCH_SIZE = 100
STATUS_MANIFEST = "indexio.status.json"


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


def _split_docs_chunker(
    docs: list,
    config: IndexioConfig,
    src: SourceConfig,
) -> list:
    """Split documents using the source's configured chunker backend."""
    from .chunkers import get_chunker

    chunker = get_chunker(
        src.chunker,
        chunk_size=config.chunk_size_chars,
        chunk_overlap=config.chunk_overlap_chars,
        options=src.chunker_options,
    )
    all_chunks: list = []
    for doc in docs:
        source_path = doc.metadata.get("source_path", "")
        chunks = chunker.chunk(
            doc.page_content,
            doc.metadata,
            source_path=source_path,
        )
        all_chunks.extend(chunks)
    return all_chunks


def _expand_braces(pattern: str) -> list[str]:
    """Expand brace patterns like ``**/*.{py,md}`` into multiple globs.

    Python's ``Path.glob`` does not support brace expansion, so we expand
    them into separate patterns: ``["**/*.py", "**/*.md"]``.
    Patterns without braces are returned as-is.
    """
    import re
    m = re.search(r'\{([^}]+)\}', pattern)
    if not m:
        return [pattern]
    prefix = pattern[:m.start()]
    suffix = pattern[m.end():]
    alternatives = [alt.strip() for alt in m.group(1).split(",")]
    expanded: list[str] = []
    for alt in alternatives:
        expanded.extend(_expand_braces(f"{prefix}{alt}{suffix}"))
    return expanded


def _source_paths(config: IndexioConfig, src: SourceConfig) -> list[Path]:
    if src.path:
        abs_path = config.root / src.path
        return [abs_path] if abs_path.exists() else []

    assert src.glob is not None

    # Expand brace patterns (e.g. **/*.{py,md} → **/*.py + **/*.md)
    glob_patterns = _expand_braces(src.glob)

    seen: set[Path] = set()
    paths: list[Path] = []
    for gp in glob_patterns:
        glob_pattern = PurePosixPath(gp)
        if glob_pattern.is_absolute():
            base = Path(glob_pattern.anchor)
            rel_pattern = str(glob_pattern.relative_to(glob_pattern.anchor))
            matched = base.glob(rel_pattern)
        else:
            base = config.root
            matched = config.root.glob(gp)

        for path in matched:
            if not path.is_file():
                continue
            if path in seen:
                continue
            rel = path.relative_to(base)
            if any(rel.match(pattern) for pattern in src.exclude):
                continue
            seen.add(path)
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


def _progress(enabled: bool, message: str) -> None:
    if enabled:
        print(message, flush=True)


def _clear_persist_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def status_manifest_path(persist_directory: Path) -> Path:
    return persist_directory / STATUS_MANIFEST


def load_status_manifest(persist_directory: Path) -> dict[str, Any] | None:
    path = status_manifest_path(persist_directory)
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"Expected mapping in {path}")
    return payload


def source_snapshot(config: IndexioConfig, src: SourceConfig) -> dict[str, Any]:
    paths = _source_paths(config, src)
    matched_paths = [
        str(path.relative_to(config.root)) if path.is_relative_to(config.root) else str(path)
        for path in paths
    ]
    file_state = {
        rel_path: {
            "mtime_ns": path.stat().st_mtime_ns,
            "size": path.stat().st_size,
        }
        for path, rel_path in zip(paths, matched_paths)
    }
    return {
        "files": len(paths),
        "matched_paths": matched_paths,
        "file_state": file_state,
    }


def _write_status_manifest(
    *,
    persist_directory: Path,
    config: IndexioConfig,
    store_name: str,
    partial: bool,
    summary: dict[str, dict[str, int]],
    selected_sources: list[SourceConfig],
) -> Path:
    existing = load_status_manifest(persist_directory) if partial else None
    payload: dict[str, Any] = {
        "version": 1,
        "built_at": datetime.now(timezone.utc).isoformat(),
        "config_path": str(config.config_path),
        "root": str(config.root),
        "store": store_name,
        "partial": partial,
        "sources": {},
    }
    if existing and isinstance(existing.get("sources"), dict):
        payload["sources"] = dict(existing["sources"])

    for src in selected_sources:
        snapshot = source_snapshot(config, src)
        payload["sources"][src.id] = {
            "id": src.id,
            "corpus": src.corpus,
            "selector": src.glob or src.path,
            "files": summary[src.id]["files"],
            "chars": summary[src.id]["chars"],
            "chunks": summary[src.id]["chunks"],
            "matched_paths": snapshot["matched_paths"],
            "file_state": snapshot["file_state"],
        }

    path = status_manifest_path(persist_directory)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


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
                    "source_path": str(path.relative_to(config.root)) if path.is_relative_to(config.root) else str(path),
                },
            )
        )
        n_files += 1
        n_chars += len(text)
    return docs, {"files": n_files, "chars": n_chars}


def _process_source(
    config: IndexioConfig,
    src: SourceConfig,
    *,
    db,
    use_upsert: bool = False,
    verbose: bool = True,
) -> dict[str, int]:
    stats = {"files": 0, "chars": 0, "chunks": 0}
    t0 = time.perf_counter()
    _progress(verbose, f"[BUILD] Reading source '{src.id}' ({src.corpus})")
    docs, base_stats = _build_documents(config, src)
    t1 = time.perf_counter()
    stats.update(base_stats)
    _progress(
        verbose,
        f"[BUILD] Source '{src.id}': loaded {stats['files']} files, {stats['chars']} chars",
    )

    if src.chunker:
        chunks = _split_docs_chunker(docs, config, src)
    else:
        chunks = _split_docs(
            docs, config.chunk_size_chars, config.chunk_overlap_chars
        )
    t2 = time.perf_counter()
    counters: dict[str, int] = {}
    for chunk in chunks:
        key = f"{chunk.metadata['source_id']}::{chunk.metadata['source_path']}"
        idx = counters.get(key, 0)
        chunk.metadata["chunk_index"] = idx
        counters[key] = idx + 1
    stats["chunks"] = len(chunks)
    _progress(verbose, f"[BUILD] Source '{src.id}': split into {stats['chunks']} chunks")

    for i in range(0, len(chunks), BATCH_SIZE):
        batch = chunks[i : i + BATCH_SIZE]
        batch_end = i + len(batch)
        _progress(
            verbose,
            f"[BUILD] Source '{src.id}': embedding batch {i + 1}-{batch_end} of {len(chunks)}",
        )
        if use_upsert:
            _db_upsert(db, documents=batch, ids=_make_chunk_ids(batch))
        else:
            db.add_documents(batch)
    t3 = time.perf_counter()

    _progress(
        verbose,
        f"[TIMER] {src.id}: load={t1 - t0:.1f}s split={t2 - t1:.1f}s embed={t3 - t2:.1f}s",
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
    verbose: bool = True,
    on_progress: ProgressCallback | None = None,
) -> dict[str, Any]:
    """Build (or rebuild) the search index.

    Args:
        on_progress: Optional callback fired per source.
            Signature: ``(source_id, source_index, total_sources, stats_or_none)``.
            Called with ``stats=None`` before processing starts, and with the
            stats dict after each source completes.
    """
    from langchain_chroma import Chroma

    _progress(verbose, f"[BUILD] Loading config: {config_path} (root={root})")
    config = load_indexio_config(config_path, root=root)
    store_cfg = resolve_store(config, store=store)
    if store_cfg.read_only:
        raise PermissionError(f"Refusing to build into read-only store '{store_cfg.name}'")

    _progress(verbose, f"[BUILD] Using store '{store_cfg.name}': {store_cfg.persist_directory}")
    _progress(verbose, f"[BUILD] Loading embedding model: {config.embedding_model}")
    embeddings = make_embeddings(config.embedding_model)
    persist_directory = store_cfg.persist_directory
    persist_directory.mkdir(parents=True, exist_ok=True)
    selected_sources = config.sources
    partial = bool(sources_filter)
    if sources_filter:
        wanted = set(sources_filter)
        selected_sources = [src for src in config.sources if src.id in wanted]
    _progress(
        verbose,
        f"[BUILD] Selected {len(selected_sources)} source(s): {', '.join(src.id for src in selected_sources) or '(none)'}",
    )

    if not partial:
        _progress(verbose, "[BUILD] Performing full rebuild: clearing existing store contents")
        _clear_persist_directory(persist_directory)
        db = Chroma(embedding_function=embeddings, persist_directory=str(persist_directory))
    else:
        db = Chroma(embedding_function=embeddings, persist_directory=str(persist_directory))
        _progress(verbose, "[BUILD] Performing partial rebuild: replacing selected sources in place")
        for src in selected_sources:
            db._collection.delete(where={"source_id": src.id})

    total = len(selected_sources)
    summary: dict[str, dict[str, int]] = {}
    for idx, src in enumerate(selected_sources):
        if on_progress:
            on_progress(src.id, idx, total, None)
        summary[src.id] = _process_source(
            config,
            src,
            db=db,
            use_upsert=partial,
            verbose=verbose,
        )
        if on_progress:
            on_progress(src.id, idx, total, summary[src.id])

    total_files = sum(item["files"] for item in summary.values())
    total_chunks = sum(item["chunks"] for item in summary.values())
    _progress(
        verbose,
        f"[BUILD] Complete: {len(summary)} source(s), {total_files} files, {total_chunks} chunks",
    )
    manifest_path = _write_status_manifest(
        persist_directory=persist_directory,
        config=config,
        store_name=store_cfg.name,
        partial=partial,
        summary=summary,
        selected_sources=selected_sources,
    )
    _progress(verbose, f"[BUILD] Wrote status manifest: {manifest_path}")

    return {
        "config_path": str(config.config_path),
        "root": str(config.root),
        "store": store_cfg.name,
        "persist_directory": str(store_cfg.persist_directory),
        "status_manifest": str(manifest_path),
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
