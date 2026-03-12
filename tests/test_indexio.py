"""Tests for the indexio core modules: config, edit, build helpers, query helpers, and CLI."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from indexio.config import (
    IndexioConfig,
    SourceConfig,
    StoreConfig,
    default_config_template,
    load_indexio_config,
    resolve_store,
    _merge_sources,
    _merge_payloads,
)
from indexio.edit import (
    OwnedSourcesSyncResult,
    ensure_raw_config,
    load_raw_config,
    replace_owned_sources,
    sync_owned_sources,
    write_raw_config,
)
from indexio.cli import main as cli_main


# ---- config: loading ---------------------------------------------------------

def test_load_basic_config(sample_config_yaml: Path, sample_project: Path) -> None:
    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    assert cfg.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.chunk_size_chars == 200
    assert cfg.chunk_overlap_chars == 50
    assert cfg.default_store == "local"
    assert "local" in cfg.stores
    assert len(cfg.sources) == 2


def test_load_config_relative_path(sample_config_yaml: Path, sample_project: Path) -> None:
    cfg = load_indexio_config(".indexio/config.yaml", root=sample_project)
    assert cfg.config_path == sample_config_yaml.resolve()


def test_load_config_defaults(tmp_path: Path) -> None:
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        """\
stores:
  local:
    persist_directory: db
sources: []
""",
        encoding="utf-8",
    )
    cfg = load_indexio_config(cfg_file, root=tmp_path)
    assert cfg.embedding_model == "sentence-transformers/all-MiniLM-L6-v2"
    assert cfg.chunk_size_chars == 1000
    assert cfg.chunk_overlap_chars == 200


def test_load_config_no_stores_raises(tmp_path: Path) -> None:
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text("sources: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at least one store"):
        load_indexio_config(cfg_file, root=tmp_path)


def test_load_config_source_both_path_and_glob_raises(tmp_path: Path) -> None:
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text(
        """\
stores:
  local:
    persist_directory: db
sources:
  - id: bad
    corpus: x
    path: foo.md
    glob: "*.md"
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one of path or glob"):
        load_indexio_config(cfg_file, root=tmp_path)


def test_load_config_source_neither_path_nor_glob_raises(tmp_path: Path) -> None:
    cfg_file = tmp_path / "bad.yaml"
    cfg_file.write_text(
        """\
stores:
  local:
    persist_directory: db
sources:
  - id: bad
    corpus: x
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="exactly one of path or glob"):
        load_indexio_config(cfg_file, root=tmp_path)


# ---- config: composition (includes) -----------------------------------------

def test_config_includes_merges_sources(
    include_configs: tuple[Path, Path], sample_project: Path
) -> None:
    overlay, _base = include_configs
    cfg = load_indexio_config(overlay, root=sample_project)
    # overlay overrides chunk_size
    assert cfg.chunk_size_chars == 300
    # base chunk_overlap preserved
    assert cfg.chunk_overlap_chars == 100
    # sources merged: docs from base + notes from overlay
    ids = {src.id for src in cfg.sources}
    assert ids == {"docs", "notes"}


def test_config_include_cycle_raises(tmp_path: Path) -> None:
    a = tmp_path / "a.yaml"
    b = tmp_path / "b.yaml"
    a.write_text(
        f"includes:\n  - b.yaml\nstores:\n  s:\n    persist_directory: db\n",
        encoding="utf-8",
    )
    b.write_text(
        f"includes:\n  - a.yaml\nstores:\n  s:\n    persist_directory: db\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="cycle"):
        load_indexio_config(a, root=tmp_path)


# ---- config: merge helpers ---------------------------------------------------

def test_merge_sources_dedup_by_id() -> None:
    base = [{"id": "a", "corpus": "x", "glob": "*.md"}]
    override = [{"id": "a", "corpus": "y", "glob": "*.txt"}]
    merged = _merge_sources(base, override)
    assert len(merged) == 1
    assert merged[0]["corpus"] == "y"


def test_merge_sources_appends_new() -> None:
    base = [{"id": "a", "corpus": "x", "glob": "*.md"}]
    override = [{"id": "b", "corpus": "y", "glob": "*.txt"}]
    merged = _merge_sources(base, override)
    assert len(merged) == 2


def test_merge_payloads_stores_merged() -> None:
    base = {"stores": {"a": {"persist_directory": "x"}}}
    override = {"stores": {"b": {"persist_directory": "y"}}}
    merged = _merge_payloads(base, override)
    assert set(merged["stores"].keys()) == {"a", "b"}


def test_merge_payloads_skips_includes_key() -> None:
    base = {"key": "val"}
    override = {"includes": ["foo.yaml"], "key": "new"}
    merged = _merge_payloads(base, override)
    assert "includes" not in merged
    assert merged["key"] == "new"


# ---- config: resolve_store --------------------------------------------------

def test_resolve_store_default(sample_config_yaml: Path, sample_project: Path) -> None:
    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    store = resolve_store(cfg)
    assert store.name == "local"


def test_resolve_store_explicit(sample_config_yaml: Path, sample_project: Path) -> None:
    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    store = resolve_store(cfg, store="local")
    assert store.name == "local"


def test_resolve_store_unknown_raises(sample_config_yaml: Path, sample_project: Path) -> None:
    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    with pytest.raises(KeyError, match="ghost"):
        resolve_store(cfg, store="ghost")


def test_resolve_store_must_exist(sample_config_yaml: Path, sample_project: Path) -> None:
    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    with pytest.raises(FileNotFoundError):
        resolve_store(cfg, store="local", must_exist=True)


def test_resolve_store_prefer_canonical(tmp_path: Path) -> None:
    cfg_file = tmp_path / "cfg.yaml"
    canon_dir = tmp_path / "canon"
    canon_dir.mkdir()
    cfg_file.write_text(
        f"""\
default_store: local
canonical_store: canon
stores:
  local:
    persist_directory: local_db
  canon:
    persist_directory: {canon_dir}
    read_only: true
sources: []
""",
        encoding="utf-8",
    )
    cfg = load_indexio_config(cfg_file, root=tmp_path)
    store = resolve_store(cfg, prefer_canonical=True)
    assert store.name == "canon"


# ---- config: default template ------------------------------------------------

def test_default_config_template_is_valid_yaml() -> None:
    payload = yaml.safe_load(default_config_template())
    assert isinstance(payload, dict)
    assert "stores" in payload
    assert "sources" in payload


# ---- config: dataclasses -----------------------------------------------------

def test_source_config_exclude_tuple() -> None:
    src = SourceConfig(id="a", corpus="b", glob="*.md", exclude=("x", "y"))
    assert src.exclude == ("x", "y")


def test_store_config_defaults() -> None:
    sc = StoreConfig(name="s", persist_directory=Path("/tmp/db"))
    assert sc.read_only is False
    assert sc.description is None


# ---- edit: raw config I/O ---------------------------------------------------

def test_write_and_load_raw_config(tmp_path: Path) -> None:
    path = tmp_path / "sub" / "cfg.yaml"
    write_raw_config(path, {"key": "value", "n": 42})
    loaded = load_raw_config(path)
    assert loaded["key"] == "value"
    assert loaded["n"] == 42


def test_ensure_raw_config_creates_new(tmp_path: Path) -> None:
    path = tmp_path / "new.yaml"
    resolved, payload, created, initialized = ensure_raw_config(path)
    assert created is True
    assert initialized is True
    assert "stores" in payload  # from default template


def test_ensure_raw_config_reads_existing(tmp_path: Path) -> None:
    path = tmp_path / "existing.yaml"
    path.write_text("foo: bar\n", encoding="utf-8")
    resolved, payload, created, initialized = ensure_raw_config(path)
    assert created is False
    assert initialized is False
    assert payload["foo"] == "bar"


# ---- edit: replace_owned_sources ---------------------------------------------

def test_replace_owned_sources_adds_new() -> None:
    payload = {"sources": [{"id": "ext", "corpus": "ext", "glob": "*.md"}]}
    merged, added, updated, removed = replace_owned_sources(
        payload,
        owned_source_ids=["mine"],
        sources=[{"id": "mine", "corpus": "my", "glob": "my/**/*.md"}],
    )
    assert "mine" in added
    assert len(updated) == 0
    assert len(removed) == 0
    ids = [s["id"] for s in merged["sources"]]
    assert ids == ["ext", "mine"]


def test_replace_owned_sources_updates_existing() -> None:
    payload = {
        "sources": [
            {"id": "mine", "corpus": "old", "glob": "old/**/*.md"},
            {"id": "ext", "corpus": "ext", "glob": "*.md"},
        ]
    }
    merged, added, updated, removed = replace_owned_sources(
        payload,
        owned_source_ids=["mine"],
        sources=[{"id": "mine", "corpus": "new", "glob": "new/**/*.md"}],
    )
    assert "mine" in updated
    assert len(added) == 0
    mine = [s for s in merged["sources"] if s["id"] == "mine"][0]
    assert mine["corpus"] == "new"


def test_replace_owned_sources_removes_stale() -> None:
    payload = {
        "sources": [
            {"id": "keep", "corpus": "a", "glob": "a/**/*.md"},
            {"id": "drop", "corpus": "b", "glob": "b/**/*.md"},
        ]
    }
    merged, added, updated, removed = replace_owned_sources(
        payload,
        owned_source_ids=["keep", "drop"],
        sources=[{"id": "keep", "corpus": "a", "glob": "a/**/*.md"}],
    )
    assert "drop" in removed
    ids = [s["id"] for s in merged["sources"]]
    assert "drop" not in ids


def test_replace_owned_sources_preserves_unowned() -> None:
    payload = {
        "sources": [
            {"id": "ext", "corpus": "ext", "glob": "*.md"},
            {"id": "mine", "corpus": "my", "glob": "my/**/*.md"},
        ]
    }
    merged, added, updated, removed = replace_owned_sources(
        payload,
        owned_source_ids=["mine"],
        sources=[],
    )
    assert "mine" in removed
    ids = [s["id"] for s in merged["sources"]]
    assert ids == ["ext"]


# ---- edit: sync_owned_sources (integration) ----------------------------------

def test_sync_owned_sources_roundtrip(tmp_path: Path) -> None:
    cfg_path = tmp_path / "indexio.yaml"
    result = sync_owned_sources(
        cfg_path,
        tmp_path,
        owned_source_ids=["s1"],
        sources=[{"id": "s1", "corpus": "c1", "glob": "c1/**/*.md"}],
    )
    assert isinstance(result, OwnedSourcesSyncResult)
    assert result.created is True
    assert "s1" in result.added

    # Second sync — update
    result2 = sync_owned_sources(
        cfg_path,
        tmp_path,
        owned_source_ids=["s1"],
        sources=[{"id": "s1", "corpus": "c1_v2", "glob": "c1/**/*.md"}],
    )
    assert result2.created is False
    assert "s1" in result2.updated


# ---- build: source_paths helper ---------------------------------------------

def test_source_paths_glob(sample_config_yaml: Path, sample_project: Path) -> None:
    from indexio.build import _source_paths

    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    docs_src = [s for s in cfg.sources if s.id == "docs"][0]
    paths = _source_paths(cfg, docs_src)
    names = {p.name for p in paths}
    assert "getting-started.md" in names
    assert "api.md" in names
    assert "tuning.md" in names


def test_source_paths_explicit_path(sample_project: Path) -> None:
    from indexio.build import _source_paths

    cfg_file = sample_project / "cfg.yaml"
    cfg_file.write_text(
        """\
stores:
  local:
    persist_directory: db
sources:
  - id: single
    corpus: single
    path: docs/api.md
""",
        encoding="utf-8",
    )
    cfg = load_indexio_config(cfg_file, root=sample_project)
    src = cfg.sources[0]
    paths = _source_paths(cfg, src)
    assert len(paths) == 1
    assert paths[0].name == "api.md"


def test_source_paths_missing_file(sample_project: Path) -> None:
    from indexio.build import _source_paths

    cfg_file = sample_project / "cfg.yaml"
    cfg_file.write_text(
        """\
stores:
  local:
    persist_directory: db
sources:
  - id: ghost
    corpus: ghost
    path: does_not_exist.md
""",
        encoding="utf-8",
    )
    cfg = load_indexio_config(cfg_file, root=sample_project)
    paths = _source_paths(cfg, cfg.sources[0])
    assert paths == []


# ---- build: document construction -------------------------------------------

def test_build_documents(sample_config_yaml: Path, sample_project: Path) -> None:
    pytest.importorskip("langchain_core")
    from indexio.build import _build_documents

    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    docs_src = [s for s in cfg.sources if s.id == "docs"][0]
    documents, stats = _build_documents(cfg, docs_src)
    assert stats["files"] == 3
    assert stats["chars"] > 0
    assert len(documents) == 3
    # check metadata
    meta = documents[0].metadata
    assert meta["source_id"] == "docs"
    assert meta["corpus"] == "docs"
    assert "source_path" in meta


def test_build_index_full_rebuild_clears_before_opening_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from indexio import build as build_mod
    from indexio.config import IndexioConfig, SourceConfig, StoreConfig

    persist_directory = tmp_path / "db"
    persist_directory.mkdir()
    (persist_directory / "stale.txt").write_text("stale\n", encoding="utf-8")

    cfg = IndexioConfig(
        root=tmp_path,
        config_path=tmp_path / ".indexio" / "config.yaml",
        embedding_model="fake-model",
        chunk_size_chars=100,
        chunk_overlap_chars=10,
        default_store="local",
        canonical_store=None,
        stores={"local": StoreConfig(name="local", persist_directory=persist_directory)},
        sources=[SourceConfig(id="docs", corpus="docs", glob="docs/**/*.md")],
    )

    events: list[str] = []

    class FakeChroma:
        def __init__(self, *, embedding_function, persist_directory: str) -> None:
            events.append("open_db")
            assert not (Path(persist_directory) / "stale.txt").exists()
            self._collection = SimpleNamespace(delete=lambda **kwargs: None)

        def add_documents(self, documents) -> None:
            return None

    monkeypatch.setattr(build_mod, "load_indexio_config", lambda config_path, root: cfg)
    monkeypatch.setattr(build_mod, "resolve_store", lambda config, store=None: cfg.stores["local"])
    monkeypatch.setattr(build_mod, "make_embeddings", lambda model_name: object())
    monkeypatch.setattr(
        build_mod,
        "_process_source",
        lambda config, src, **kwargs: events.append(f"process_{src.id}") or {"files": 0, "chars": 0, "chunks": 0},
    )
    monkeypatch.setitem(sys.modules, "langchain_chroma", SimpleNamespace(Chroma=FakeChroma))

    payload = build_mod.build_index(config_path=".indexio/config.yaml", root=tmp_path, verbose=False)
    assert payload["partial"] is False
    assert events == ["open_db", "process_docs"]
    assert persist_directory.exists()
    assert not (persist_directory / "stale.txt").exists()


# ---- build: chunk id generation ----------------------------------------------

def test_make_chunk_ids() -> None:
    from indexio.build import _make_chunk_ids

    class FakeChunk:
        def __init__(self, source_id: str, source_path: str, chunk_index: int) -> None:
            self.metadata = {
                "source_id": source_id,
                "source_path": source_path,
                "chunk_index": chunk_index,
            }

    chunks = [
        FakeChunk("docs", "a.md", 0),
        FakeChunk("docs", "a.md", 1),
        FakeChunk("docs", "b.md", 0),
    ]
    ids = _make_chunk_ids(chunks)
    assert ids == ["docs::a.md::0", "docs::a.md::1", "docs::b.md::0"]


# ---- query: doc_to_result ---------------------------------------------------

def test_doc_to_result() -> None:
    from indexio.query import _doc_to_result

    class FakeDoc:
        def __init__(self) -> None:
            self.page_content = "  Hello\nworld  "
            self.metadata = {
                "corpus": "docs",
                "source_id": "docs",
                "source_path": "a.md",
                "chunk_index": 0,
            }

    result = _doc_to_result(FakeDoc())
    assert result["corpus"] == "docs"
    assert result["source_path"] == "a.md"
    assert result["chunk_index"] == 0
    assert "Hello" in result["snippet"]
    assert "\n" not in result["snippet"]  # newlines replaced


def test_doc_to_result_truncates_long_snippet() -> None:
    from indexio.query import _doc_to_result

    class FakeDoc:
        def __init__(self) -> None:
            self.page_content = "x" * 500
            self.metadata = {}

    result = _doc_to_result(FakeDoc())
    assert len(result["snippet"]) == 400


# ---- CLI: init --------------------------------------------------------

def test_cli_init_config(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    cli_main(["init", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[OK]" in out
    generated = tmp_path / ".indexio" / "config.yaml"
    assert generated.exists()
    payload = yaml.safe_load(generated.read_text(encoding="utf-8"))
    assert "stores" in payload


def test_cli_init_config_skip_existing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / ".indexio" / "config.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("existing: true\n", encoding="utf-8")
    cli_main(["init", "--root", str(tmp_path)])
    out = capsys.readouterr().out
    assert "[SKIP]" in out
    # content unchanged
    assert "existing: true" in output.read_text(encoding="utf-8")


def test_cli_init_config_force(tmp_path: Path) -> None:
    output = tmp_path / ".indexio" / "config.yaml"
    output.parent.mkdir(parents=True)
    output.write_text("old: true\n", encoding="utf-8")
    cli_main(["init", "--root", str(tmp_path), "--force"])
    payload = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert "stores" in payload
    assert "old" not in payload


# ---- CLI: status -------------------------------------------------------------

def test_cli_status(
    sample_config_yaml: Path, sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    cli_main(["status", "--config", str(sample_config_yaml), "--root", str(sample_project)])
    out = capsys.readouterr().out
    assert "On store 'local'" in out
    assert "Manifest: missing" in out
    assert "not yet built:" in out
    assert "docs (docs)" in out


def test_cli_status_uses_default_root_and_config(
    sample_project: Path,
    sample_config_yaml: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert sample_config_yaml.exists()
    monkeypatch.chdir(sample_project)
    cli_main(["status"])
    out = capsys.readouterr().out
    assert ".indexio/config.yaml" in out
    assert "On store 'local'" in out


def test_cli_status_reports_changed_source_from_manifest(
    sample_config_yaml: Path, sample_project: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from indexio.build import status_manifest_path
    from indexio.config import load_indexio_config, resolve_store

    cfg = load_indexio_config(sample_config_yaml, root=sample_project)
    store = resolve_store(cfg)
    store.persist_directory.mkdir(parents=True, exist_ok=True)
    manifest = {
        "version": 1,
        "built_at": "2026-03-12T12:00:00+00:00",
        "sources": {
            "docs": {
                "id": "docs",
                "corpus": "docs",
                "selector": "docs/**/*.md",
                "files": 1,
                "chars": 10,
                "chunks": 2,
                "matched_paths": ["docs/getting-started.md"],
                "file_state": {"docs/getting-started.md": {"mtime_ns": 1, "size": 1}},
            }
        },
    }
    status_manifest_path(store.persist_directory).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    cli_main(["status", "--config", str(sample_config_yaml), "--root", str(sample_project)])
    out = capsys.readouterr().out
    assert "Manifest: present" in out
    assert "changed:" in out
    assert "docs (docs)" in out
    assert "Actions:" in out


def test_cli_build_prints_completion_and_passes_verbose(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    called: dict[str, object] = {}

    def fake_build_index(**kwargs):
        called.update(kwargs)
        print("[BUILD] Complete: 1 source(s), 2 files, 3 chunks")
        return {"ok": True}

    monkeypatch.setattr("indexio.cli.build_mod.build_index", fake_build_index)
    cli_main(["build"])
    out = capsys.readouterr().out
    assert "[BUILD] Complete" in out
    assert "[INFO] Index build complete." in out
    assert called["config_path"] == ".indexio/config.yaml"
    assert called["root"] == "."
    assert called["verbose"] is True


def test_cli_build_json_suppresses_progress(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    called: dict[str, object] = {}

    def fake_build_index(**kwargs):
        called.update(kwargs)
        return {"ok": True}

    monkeypatch.setattr("indexio.cli.build_mod.build_index", fake_build_index)
    cli_main(["build", "--json"])
    out = capsys.readouterr().out
    assert out.strip() == '{\n  "ok": true\n}'
    assert called["verbose"] is False


def test_resolve_bind_port_prefers_requested_port(monkeypatch: pytest.MonkeyPatch) -> None:
    from indexio.cli import _resolve_bind_port

    monkeypatch.setattr("indexio.cli._port_available", lambda host, port: port == 9100)
    port, changed = _resolve_bind_port("127.0.0.1", 9100)
    assert port == 9100
    assert changed is False


def test_resolve_bind_port_falls_forward(monkeypatch: pytest.MonkeyPatch) -> None:
    from indexio.cli import _resolve_bind_port

    monkeypatch.setattr("indexio.cli._port_available", lambda host, port: port == 9102)
    port, changed = _resolve_bind_port("127.0.0.1", 9100, max_tries=5)
    assert port == 9102
    assert changed is True


def test_resolve_bind_port_raises_when_no_port_available(monkeypatch: pytest.MonkeyPatch) -> None:
    from indexio.cli import _resolve_bind_port

    monkeypatch.setattr("indexio.cli._port_available", lambda host, port: False)
    with pytest.raises(RuntimeError, match="Could not find a free port"):
        _resolve_bind_port("127.0.0.1", 9100, max_tries=2)
