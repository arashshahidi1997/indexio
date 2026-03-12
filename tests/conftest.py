"""Shared fixtures for indexio tests."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture()
def sample_project(tmp_path: Path) -> Path:
    """Create a minimal project tree with markdown files for indexing."""
    # docs
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "getting-started.md").write_text(
        "# Getting Started\n\nThis guide explains how to set up the project.\n",
        encoding="utf-8",
    )
    (docs / "api.md").write_text(
        "# API Reference\n\nThe main endpoint is `/v1/search`.\n",
        encoding="utf-8",
    )

    # nested docs
    nested = docs / "advanced"
    nested.mkdir()
    (nested / "tuning.md").write_text(
        "# Tuning\n\nAdjust chunk_size and overlap for better results.\n",
        encoding="utf-8",
    )

    # code file (for exclude tests)
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello')\n", encoding="utf-8")

    return tmp_path


@pytest.fixture()
def sample_config_yaml(sample_project: Path) -> Path:
    """Write a minimal indexio config YAML and return its path."""
    config_dir = sample_project / "infra" / "indexio"
    config_dir.mkdir(parents=True)
    config_file = config_dir / "config.yaml"
    config_file.write_text(
        f"""\
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
chunk_size_chars: 200
chunk_overlap_chars: 50
default_store: local

stores:
  local:
    persist_directory: .cache/indexio/chroma_db
    read_only: false
    description: "Test store"

sources:
  - id: docs
    corpus: docs
    glob: "docs/**/*.md"

  - id: code
    corpus: code
    glob: "src/**/*.py"
""",
        encoding="utf-8",
    )
    return config_file


@pytest.fixture()
def include_configs(sample_project: Path) -> tuple[Path, Path]:
    """Write a base config and an overlay that includes it."""
    config_dir = sample_project / "infra" / "indexio"
    config_dir.mkdir(parents=True, exist_ok=True)

    base = config_dir / "base.yaml"
    base.write_text(
        """\
embedding_model: "sentence-transformers/all-MiniLM-L6-v2"
chunk_size_chars: 500
chunk_overlap_chars: 100
default_store: local

stores:
  local:
    persist_directory: .cache/indexio/chroma_db
    read_only: false

sources:
  - id: docs
    corpus: docs
    glob: "docs/**/*.md"
""",
        encoding="utf-8",
    )

    overlay = config_dir / "config.yaml"
    overlay.write_text(
        f"""\
includes:
  - base.yaml

chunk_size_chars: 300

sources:
  - id: notes
    corpus: notes
    glob: "notes/**/*.md"
""",
        encoding="utf-8",
    )

    return overlay, base
