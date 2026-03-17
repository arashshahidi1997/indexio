"""Tests for indexio.chunkers — text, ast, and code chunking backends."""
from __future__ import annotations

import pytest

from indexio.chunkers import (
    AstChunker,
    CodeChunker,
    TextChunker,
    _ast_extract_symbols,
    get_chunker,
)


SAMPLE_PYTHON = '''\
"""Module docstring."""

import os

X = 42


def greet(name: str) -> str:
    """Say hello."""
    return f"Hello, {name}"


class Calculator:
    """A simple calculator."""

    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b


async def fetch_data(url: str):
    """Fetch data from URL."""
    return url
'''

SAMPLE_NON_PYTHON = """\
# Getting Started

This is a markdown document with some content.

## Installation

Run `pip install indexio` to install.
"""


# ---- ast symbol extraction --------------------------------------------------

def test_ast_extract_symbols_finds_functions_and_classes() -> None:
    symbols = _ast_extract_symbols(SAMPLE_PYTHON)
    names = [s["symbol_name"] for s in symbols]
    assert "greet" in names
    assert "Calculator" in names
    assert "Calculator.add" in names
    assert "Calculator.subtract" in names
    assert "fetch_data" in names


def test_ast_extract_symbols_captures_line_ranges() -> None:
    symbols = _ast_extract_symbols(SAMPLE_PYTHON)
    greet = [s for s in symbols if s["symbol_name"] == "greet"][0]
    assert greet["symbol_type"] == "function"
    assert greet["start_line"] > 0
    assert greet["end_line"] >= greet["start_line"]


def test_ast_extract_symbols_handles_syntax_error() -> None:
    symbols = _ast_extract_symbols("def broken(")
    assert symbols == []


def test_ast_extract_symbols_methods_have_correct_type() -> None:
    symbols = _ast_extract_symbols(SAMPLE_PYTHON)
    add = [s for s in symbols if s["symbol_name"] == "Calculator.add"][0]
    assert add["symbol_type"] == "method"


def test_ast_extract_symbols_async_function() -> None:
    symbols = _ast_extract_symbols(SAMPLE_PYTHON)
    fetch = [s for s in symbols if s["symbol_name"] == "fetch_data"][0]
    assert fetch["symbol_type"] == "function"


# ---- get_chunker factory ----------------------------------------------------

def test_get_chunker_default_returns_text() -> None:
    chunker = get_chunker(None)
    assert isinstance(chunker, TextChunker)


def test_get_chunker_text() -> None:
    chunker = get_chunker("text")
    assert isinstance(chunker, TextChunker)


def test_get_chunker_ast() -> None:
    chunker = get_chunker("ast")
    assert isinstance(chunker, AstChunker)


def test_get_chunker_code() -> None:
    chunker = get_chunker("code")
    assert isinstance(chunker, CodeChunker)


def test_get_chunker_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown chunker"):
        get_chunker("nonexistent")


def test_get_chunker_passes_options() -> None:
    chunker = get_chunker("ast", options={"max_chunk_chars": 5000})
    assert isinstance(chunker, AstChunker)
    assert chunker.max_chunk_chars == 5000


# ---- TextChunker -----------------------------------------------------------

def test_text_chunker_produces_chunks() -> None:
    pytest.importorskip("langchain_core")
    chunker = TextChunker(chunk_size=50, chunk_overlap=10)
    chunks = chunker.chunk(
        SAMPLE_PYTHON,
        {"source_id": "test", "corpus": "code"},
        source_path="test.py",
    )
    assert len(chunks) > 1
    for c in chunks:
        assert c.metadata["source_id"] == "test"


# ---- AstChunker ------------------------------------------------------------

def test_ast_chunker_splits_python_by_symbol() -> None:
    pytest.importorskip("langchain_core")
    chunker = AstChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk(
        SAMPLE_PYTHON,
        {"source_id": "test", "corpus": "code"},
        source_path="src/utils.py",
    )
    symbol_names = [c.metadata.get("symbol_name") for c in chunks]
    assert "greet" in symbol_names
    assert "Calculator" in symbol_names
    assert "Calculator.add" in symbol_names
    # All chunks should have language metadata
    for c in chunks:
        assert c.metadata.get("language") == "python"


def test_ast_chunker_falls_back_for_non_python() -> None:
    pytest.importorskip("langchain_core")
    chunker = AstChunker(chunk_size=50, chunk_overlap=10)
    chunks = chunker.chunk(
        SAMPLE_NON_PYTHON,
        {"source_id": "docs", "corpus": "docs"},
        source_path="README.md",
    )
    # Should still produce chunks (via text fallback)
    assert len(chunks) >= 1
    # No symbol metadata since it's not Python
    assert "symbol_name" not in chunks[0].metadata


def test_ast_chunker_falls_back_on_syntax_error() -> None:
    pytest.importorskip("langchain_core")
    chunker = AstChunker(chunk_size=50, chunk_overlap=10)
    chunks = chunker.chunk(
        "def broken(",
        {"source_id": "test", "corpus": "code"},
        source_path="bad.py",
    )
    # Falls back to text chunker
    assert len(chunks) >= 1


def test_ast_chunker_includes_module_level_code() -> None:
    pytest.importorskip("langchain_core")
    chunker = AstChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk(
        SAMPLE_PYTHON,
        {"source_id": "test", "corpus": "code"},
        source_path="test.py",
    )
    module_chunks = [
        c for c in chunks if c.metadata.get("symbol_name") == "<module>"
    ]
    assert len(module_chunks) == 1
    # Module chunk should contain imports and module-level assignments
    assert "import os" in module_chunks[0].page_content


def test_ast_chunker_subsplits_large_symbols() -> None:
    pytest.importorskip("langchain_core")
    big_func = "def big():\n" + "    x = 1\n" * 200
    chunker = AstChunker(
        chunk_size=100, chunk_overlap=10, max_chunk_chars=50,
    )
    chunks = chunker.chunk(
        big_func,
        {"source_id": "test", "corpus": "code"},
        source_path="big.py",
    )
    # Should have multiple chunks from the sub-split
    assert len(chunks) > 1


# ---- CodeChunker (tree-sitter) ---------------------------------------------

def test_code_chunker_falls_back_without_tree_sitter() -> None:
    """When tree-sitter is not installed, CodeChunker falls back to ast."""
    pytest.importorskip("langchain_core")
    chunker = CodeChunker(chunk_size=200, chunk_overlap=20)
    chunks = chunker.chunk(
        SAMPLE_PYTHON,
        {"source_id": "test", "corpus": "code"},
        source_path="src/utils.py",
    )
    # Should still produce structured chunks (via ast fallback)
    assert len(chunks) > 0
    symbol_names = [c.metadata.get("symbol_name") for c in chunks]
    # ast fallback should find the same symbols
    assert "greet" in symbol_names or any(
        "greet" in (n or "") for n in symbol_names
    )


def test_code_chunker_non_python_falls_back_to_text() -> None:
    pytest.importorskip("langchain_core")
    chunker = CodeChunker(chunk_size=50, chunk_overlap=10)
    chunks = chunker.chunk(
        SAMPLE_NON_PYTHON,
        {"source_id": "docs", "corpus": "docs"},
        source_path="README.md",
    )
    assert len(chunks) >= 1


def test_code_chunker_respects_language_filter() -> None:
    pytest.importorskip("langchain_core")
    # Only allow javascript — Python should fall back to text
    chunker = CodeChunker(
        chunk_size=50, chunk_overlap=10, languages=["javascript"],
    )
    chunks = chunker.chunk(
        SAMPLE_PYTHON,
        {"source_id": "test", "corpus": "code"},
        source_path="test.py",
    )
    # Should produce text chunks (no symbol metadata)
    assert len(chunks) >= 1
    assert "symbol_name" not in chunks[0].metadata


# ---- Config integration ----------------------------------------------------

def test_source_config_chunker_field() -> None:
    from indexio.config import SourceConfig
    src = SourceConfig(
        id="code",
        corpus="code",
        glob="src/**/*.py",
        chunker="ast",
        chunker_options={"max_chunk_chars": 5000},
    )
    assert src.chunker == "ast"
    assert src.chunker_options == {"max_chunk_chars": 5000}


def test_source_config_chunker_default_none() -> None:
    from indexio.config import SourceConfig
    src = SourceConfig(id="docs", corpus="docs", glob="docs/**/*.md")
    assert src.chunker is None
    assert src.chunker_options is None


def test_config_parses_chunker_field(tmp_path) -> None:
    from indexio.config import load_indexio_config
    cfg_file = tmp_path / "cfg.yaml"
    cfg_file.write_text(
        """\
stores:
  local:
    persist_directory: db
sources:
  - id: code
    corpus: code
    glob: "src/**/*.py"
    chunker: ast
    chunker_options:
      max_chunk_chars: 5000
  - id: docs
    corpus: docs
    glob: "docs/**/*.md"
""",
        encoding="utf-8",
    )
    cfg = load_indexio_config(cfg_file, root=tmp_path)
    code_src = [s for s in cfg.sources if s.id == "code"][0]
    docs_src = [s for s in cfg.sources if s.id == "docs"][0]
    assert code_src.chunker == "ast"
    assert code_src.chunker_options == {"max_chunk_chars": 5000}
    assert docs_src.chunker is None
    assert docs_src.chunker_options is None
