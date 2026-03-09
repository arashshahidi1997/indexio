from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

import yaml

from .config import default_config_template


@dataclass(frozen=True)
class OwnedSourcesSyncResult:
    config_path: Path
    created: bool
    initialized: bool
    added: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]


def load_raw_config(config_path: str | Path) -> dict[str, Any]:
    path = Path(config_path).expanduser().resolve()
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise TypeError(f"Expected mapping in {path}")
    return payload


def write_raw_config(config_path: str | Path, payload: Mapping[str, Any]) -> Path:
    path = Path(config_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(dict(payload), sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )
    return path


def ensure_raw_config(
    config_path: str | Path,
    *,
    force_init: bool = False,
    template: str | None = None,
) -> tuple[Path, dict[str, Any], bool, bool]:
    path = Path(config_path).expanduser().resolve()
    created = not path.exists()
    initialized = created or force_init
    if initialized:
        payload = yaml.safe_load(template or default_config_template()) or {}
        if not isinstance(payload, dict):
            raise TypeError(f"Expected mapping in template for {path}")
        return path, payload, created, True
    return path, load_raw_config(path), False, False


def replace_owned_sources(
    payload: Mapping[str, Any],
    *,
    owned_source_ids: Iterable[str],
    sources: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    owned = set(owned_source_ids)
    current_sources = payload.get("sources") or []
    if not isinstance(current_sources, list):
        raise TypeError("sources must be a list")

    existing_owned: dict[str, dict[str, Any]] = {}
    preserved: list[Any] = []
    for raw in current_sources:
        if not isinstance(raw, dict):
            preserved.append(raw)
            continue
        raw_id = raw.get("id")
        if isinstance(raw_id, str) and raw_id in owned:
            existing_owned[raw_id] = dict(raw)
            continue
        preserved.append(raw)

    new_sources: list[dict[str, Any]] = []
    added: list[str] = []
    updated: list[str] = []
    for raw in sources:
        src = dict(raw)
        src_id = str(src["id"])
        new_sources.append(src)
        previous = existing_owned.get(src_id)
        if previous is None:
            added.append(src_id)
        elif previous != src:
            updated.append(src_id)

    removed = sorted(src_id for src_id in existing_owned if src_id not in {src["id"] for src in new_sources})

    merged = dict(payload)
    merged["sources"] = [*preserved, *new_sources]
    return merged, tuple(sorted(added)), tuple(sorted(updated)), tuple(removed)


def sync_owned_sources(
    config_path: str | Path,
    root: str | Path,
    *,
    owned_source_ids: Iterable[str],
    sources: Iterable[Mapping[str, Any]],
    force_init: bool = False,
    template: str | None = None,
) -> OwnedSourcesSyncResult:
    path, payload, created, initialized = ensure_raw_config(
        config_path,
        force_init=force_init,
        template=template,
    )
    merged, added, updated, removed = replace_owned_sources(
        payload,
        owned_source_ids=owned_source_ids,
        sources=sources,
    )
    write_raw_config(path, merged)
    return OwnedSourcesSyncResult(
        config_path=path,
        created=created,
        initialized=initialized,
        added=added,
        updated=updated,
        removed=removed,
    )
