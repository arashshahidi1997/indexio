from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_REL = Path("infra/indexio/config.yaml")


def _resolve_path(path: str | Path, root: Path) -> Path:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return (root / candidate).resolve()


@dataclass(frozen=True)
class StoreConfig:
    name: str
    persist_directory: Path
    read_only: bool = False
    description: str | None = None


@dataclass(frozen=True)
class SourceConfig:
    id: str
    corpus: str
    path: str | None = None
    glob: str | None = None
    exclude: tuple[str, ...] = ()


@dataclass(frozen=True)
class IndexioConfig:
    root: Path
    config_path: Path
    embedding_model: str
    chunk_size_chars: int
    chunk_overlap_chars: int
    default_store: str
    canonical_store: str | None
    stores: dict[str, StoreConfig] = field(default_factory=dict)
    sources: list[SourceConfig] = field(default_factory=list)


def default_config_template() -> str:
    return """# indexio config
#
# Copy this file into your repo, then customize the source globs.
# The local store is a per-clone writable cache.
#
# You can compose from smaller configs:
#
# includes:
#   - bib/config/indexio.yaml

embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
chunk_size_chars: 1000
chunk_overlap_chars: 200

default_store: local

stores:
  local:
    persist_directory: .cache/indexio/chroma_db
    read_only: false
    description: "Per-clone writable Chroma cache"

sources:
  - id: "docs"
    corpus: "docs"
    glob: "docs/**/*.md"
"""


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"Expected mapping in {path}")
    return payload


def _merge_sources(base: list[Any], override: list[Any]) -> list[Any]:
    merged: list[Any] = []
    index_by_id: dict[str, int] = {}
    for raw in [*base, *override]:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            src_id = str(raw["id"])
            if src_id in index_by_id:
                merged[index_by_id[src_id]] = dict(raw)
            else:
                index_by_id[src_id] = len(merged)
                merged.append(dict(raw))
        else:
            merged.append(raw)
    return merged


def _merge_payloads(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if key == "includes":
            continue
        if key == "stores" and isinstance(merged.get(key), dict) and isinstance(value, dict):
            store_map = dict(merged[key])
            for store_name, store_value in value.items():
                store_map[store_name] = store_value
            merged[key] = store_map
            continue
        if key == "sources" and isinstance(merged.get(key), list) and isinstance(value, list):
            merged[key] = _merge_sources(list(merged[key]), value)
            continue
        merged[key] = value
    return merged


def _load_composed_payload(config_file: Path, *, seen: set[Path] | None = None) -> dict[str, Any]:
    resolved = config_file.expanduser().resolve()
    visited = set() if seen is None else set(seen)
    if resolved in visited:
        raise ValueError(f"indexio config include cycle detected at {resolved}")
    visited.add(resolved)

    payload = _load_yaml_mapping(resolved)
    includes = payload.get("includes") or []
    if includes and not isinstance(includes, list):
        raise TypeError(f"includes must be a list in {resolved}")

    merged: dict[str, Any] = {}
    for raw_include in includes:
        include_path = Path(str(raw_include)).expanduser()
        if not include_path.is_absolute():
            include_path = (resolved.parent / include_path).resolve()
        merged = _merge_payloads(merged, _load_composed_payload(include_path, seen=visited))
    return _merge_payloads(merged, payload)


def _coerce_store_configs(
    payload: dict[str, Any], root: Path
) -> tuple[str, str | None, dict[str, StoreConfig]]:
    stores_payload = payload.get("stores") or {}
    if not stores_payload:
        raise ValueError("Config must define at least one store under 'stores'")
    stores: dict[str, StoreConfig] = {}
    for name, raw in stores_payload.items():
        if not isinstance(raw, dict):
            raise TypeError(f"Store '{name}' must be a mapping")
        persist_directory = raw.get("persist_directory")
        if not persist_directory:
            raise ValueError(f"Store '{name}' is missing persist_directory")
        stores[name] = StoreConfig(
            name=name,
            persist_directory=_resolve_path(str(persist_directory), root),
            read_only=bool(raw.get("read_only", False)),
            description=raw.get("description"),
        )
    default_store = str(payload.get("default_store") or next(iter(stores)))
    canonical_store_raw = payload.get("canonical_store")
    canonical_store = str(canonical_store_raw) if canonical_store_raw else None
    return default_store, canonical_store, stores


def load_indexio_config(config_path: str | Path, root: str | Path) -> IndexioConfig:
    """Load and parse an indexio YAML config.

    Args:
        config_path: Path to the YAML config file (absolute or relative to root).
        root: Explicit project root used to resolve relative paths.
    """
    root_path = Path(root).expanduser().resolve()
    raw = Path(config_path).expanduser()
    config_file = raw if raw.is_absolute() else (root_path / raw).resolve()

    payload = _load_composed_payload(config_file)
    path_root = payload.get("path_root")
    if path_root:
        root_path = _resolve_path(str(path_root), config_file.parent)

    default_store, canonical_store, stores = _coerce_store_configs(payload, root_path)
    sources: list[SourceConfig] = []
    for raw_src in payload.get("sources", []) or []:
        if not isinstance(raw_src, dict):
            raise TypeError("Each source must be a mapping")
        src = SourceConfig(
            id=str(raw_src["id"]),
            corpus=str(raw_src["corpus"]),
            path=str(raw_src["path"]) if "path" in raw_src else None,
            glob=str(raw_src["glob"]) if "glob" in raw_src else None,
            exclude=tuple(str(item) for item in raw_src.get("exclude", []) or []),
        )
        if bool(src.path) == bool(src.glob):
            raise ValueError(f"Source '{src.id}' must define exactly one of path or glob")
        sources.append(src)

    return IndexioConfig(
        root=root_path,
        config_path=config_file,
        embedding_model=str(payload.get("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")),
        chunk_size_chars=int(payload.get("chunk_size_chars", 1000)),
        chunk_overlap_chars=int(payload.get("chunk_overlap_chars", 200)),
        default_store=default_store,
        canonical_store=canonical_store,
        stores=stores,
        sources=sources,
    )


def resolve_store(
    config: IndexioConfig,
    *,
    store: str | None = None,
    prefer_canonical: bool = False,
    must_exist: bool = False,
) -> StoreConfig:
    chosen = store
    if chosen is None and prefer_canonical and config.canonical_store:
        candidate = config.stores.get(config.canonical_store)
        if candidate is not None and candidate.persist_directory.exists():
            chosen = candidate.name
    if chosen is None:
        chosen = config.default_store
    if chosen not in config.stores:
        raise KeyError(f"Unknown store '{chosen}'. Available: {sorted(config.stores)}")
    resolved = config.stores[chosen]
    if must_exist and not resolved.persist_directory.exists():
        raise FileNotFoundError(f"Store does not exist: {resolved.persist_directory}")
    return resolved