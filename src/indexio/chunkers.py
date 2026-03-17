"""Pluggable chunking backends for indexio.

Each backend takes raw document text + metadata and returns a list of
LangChain Document objects representing individual chunks.

Available backends:
    text  — default character-based splitter (RecursiveCharacterTextSplitter)
    ast   — Python stdlib ast: splits by function/class (zero extra deps)
    code  — tree-sitter: language-aware structural chunking (optional dep)
"""
from __future__ import annotations

from typing import Any, Protocol


class Chunker(Protocol):
    """Minimal interface every chunking backend must satisfy."""

    def chunk(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        source_path: str,
    ) -> list:  # list[Document]
        ...


# ---------------------------------------------------------------------------
# text — default backend (existing behaviour)
# ---------------------------------------------------------------------------

class TextChunker:
    """Character-based recursive text splitter (LangChain)."""

    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def chunk(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        source_path: str,
    ) -> list:
        from langchain_core.documents import Document
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            length_function=len,
        )
        doc = Document(page_content=text, metadata=dict(metadata))
        return splitter.split_documents([doc])


# ---------------------------------------------------------------------------
# ast — Python stdlib ast backend (no extra deps)
# ---------------------------------------------------------------------------

def _ast_extract_symbols(source: str) -> list[dict[str, Any]]:
    """Parse Python source with stdlib ast; return symbol ranges."""
    import ast as _ast

    try:
        tree = _ast.parse(source)
    except SyntaxError:
        return []

    symbols: list[dict[str, Any]] = []
    for node in _ast.iter_child_nodes(tree):
        if isinstance(node, (_ast.FunctionDef, _ast.AsyncFunctionDef)):
            symbols.append({
                "symbol_name": node.name,
                "symbol_type": "function",
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
            })
        elif isinstance(node, _ast.ClassDef):
            symbols.append({
                "symbol_name": node.name,
                "symbol_type": "class",
                "start_line": node.lineno,
                "end_line": node.end_lineno or node.lineno,
            })
            # Also extract methods inside the class
            for child in _ast.iter_child_nodes(node):
                if isinstance(
                    child, (_ast.FunctionDef, _ast.AsyncFunctionDef)
                ):
                    symbols.append({
                        "symbol_name": f"{node.name}.{child.name}",
                        "symbol_type": "method",
                        "start_line": child.lineno,
                        "end_line": child.end_lineno or child.lineno,
                    })
    return symbols


class AstChunker:
    """Chunk Python files by function/class using stdlib ast.

    Falls back to TextChunker for non-Python files or on parse failure.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        include_docstrings: bool = True,
        max_chunk_chars: int = 3000,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_docstrings = include_docstrings
        self.max_chunk_chars = max_chunk_chars
        self._fallback = TextChunker(chunk_size, chunk_overlap)

    def chunk(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        source_path: str,
    ) -> list:
        from langchain_core.documents import Document

        if not source_path.endswith(".py"):
            return self._fallback.chunk(
                text, metadata, source_path=source_path
            )

        symbols = _ast_extract_symbols(text)
        if not symbols:
            return self._fallback.chunk(
                text, metadata, source_path=source_path
            )

        lines = text.splitlines(keepends=True)
        chunks: list[Document] = []
        for sym in symbols:
            start = sym["start_line"] - 1  # 0-based
            end = sym["end_line"]
            body = "".join(lines[start:end])
            if not self.include_docstrings:
                pass  # could strip docstrings later
            if len(body) > self.max_chunk_chars:
                # Oversized symbol: sub-split with text chunker
                sub_meta = {**metadata, **sym, "language": "python"}
                sub_chunks = self._fallback.chunk(
                    body, sub_meta, source_path=source_path
                )
                chunks.extend(sub_chunks)
            else:
                meta = {**metadata, **sym, "language": "python"}
                chunks.append(Document(page_content=body, metadata=meta))

        # Include module-level code (lines not covered by any symbol)
        covered = set()
        for sym in symbols:
            for i in range(sym["start_line"] - 1, sym["end_line"]):
                covered.add(i)
        uncovered_lines = [
            lines[i] for i in range(len(lines)) if i not in covered
        ]
        module_text = "".join(uncovered_lines).strip()
        if module_text:
            meta = {
                **metadata,
                "symbol_name": "<module>",
                "symbol_type": "module",
                "language": "python",
                "start_line": 1,
                "end_line": len(lines),
            }
            chunks.append(Document(page_content=module_text, metadata=meta))

        return chunks


# ---------------------------------------------------------------------------
# code — tree-sitter backend (optional dependency)
# ---------------------------------------------------------------------------

_LANGUAGE_EXTENSIONS: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".rb": "ruby",
}

# tree-sitter node types that represent top-level symbols per language
_SYMBOL_NODE_TYPES: dict[str, set[str]] = {
    "python": {
        "function_definition",
        "class_definition",
        "decorated_definition",
    },
    "javascript": {
        "function_declaration",
        "class_declaration",
        "export_statement",
        "lexical_declaration",
    },
    "typescript": {
        "function_declaration",
        "class_declaration",
        "export_statement",
        "lexical_declaration",
        "interface_declaration",
        "type_alias_declaration",
    },
    "go": {
        "function_declaration",
        "method_declaration",
        "type_declaration",
    },
    "rust": {"function_item", "impl_item", "struct_item", "enum_item"},
    "java": {
        "class_declaration",
        "interface_declaration",
        "method_declaration",
    },
    "c": {"function_definition", "struct_specifier", "enum_specifier"},
    "cpp": {"function_definition", "class_specifier", "struct_specifier"},
    "ruby": {"method", "class", "module"},
}


def _get_tree_sitter_language(lang: str):
    """Lazily import and return a tree-sitter Language for *lang*."""
    try:
        import importlib
        mod = importlib.import_module(f"tree_sitter_{lang}")
        return mod.language()
    except (ImportError, AttributeError) as exc:
        raise ImportError(
            f"tree-sitter grammar for '{lang}' not installed. "
            f"Install with: pip install tree-sitter-{lang}"
        ) from exc


def _ts_extract_symbols(
    source_bytes: bytes,
    language_name: str,
) -> list[dict[str, Any]]:
    """Extract top-level symbols using tree-sitter."""
    try:
        import tree_sitter
    except ImportError as exc:
        raise ImportError(
            "tree-sitter is required for the 'code' chunker. "
            "Install with: pip install indexio[code]"
        ) from exc

    lang = _get_tree_sitter_language(language_name)
    parser = tree_sitter.Parser(lang)
    tree = parser.parse(source_bytes)

    node_types = _SYMBOL_NODE_TYPES.get(language_name, set())
    symbols: list[dict[str, Any]] = []

    def _symbol_name(node) -> str:
        """Best-effort name extraction from a tree-sitter node."""
        for child in node.children:
            if child.type in ("identifier", "name", "property_identifier"):
                return child.text.decode("utf-8", errors="replace")
        return "<anonymous>"

    def _symbol_type(node, language_name: str) -> str:
        t = node.type
        if "class" in t:
            return "class"
        if "method" in t:
            return "method"
        if "function" in t:
            return "function"
        if "interface" in t or "type_alias" in t:
            return "type"
        if "struct" in t or "enum" in t:
            return "type"
        if "impl" in t:
            return "impl"
        return "declaration"

    for child in tree.root_node.children:
        if child.type in node_types:
            symbols.append({
                "symbol_name": _symbol_name(child),
                "symbol_type": _symbol_type(child, language_name),
                "start_line": child.start_point[0] + 1,
                "end_line": child.end_point[0] + 1,
            })
            # For classes, also extract methods
            if "class" in child.type:
                body = None
                for sub in child.children:
                    if sub.type in ("block", "class_body", "body"):
                        body = sub
                        break
                if body:
                    method_types = {
                        t for t in node_types if "function" in t or "method" in t
                    }
                    for member in body.children:
                        if member.type in method_types or (
                            member.type == "decorated_definition"
                        ):
                            class_name = _symbol_name(child)
                            method_name = _symbol_name(member)
                            symbols.append({
                                "symbol_name": (
                                    f"{class_name}.{method_name}"
                                ),
                                "symbol_type": "method",
                                "start_line": member.start_point[0] + 1,
                                "end_line": member.end_point[0] + 1,
                            })

    return symbols


class CodeChunker:
    """Tree-sitter based structural code chunker.

    Falls back to AstChunker (for Python) or TextChunker for unsupported
    languages or when tree-sitter is not installed.
    """

    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        max_chunk_chars: int = 3000,
        languages: list[str] | None = None,
    ) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.max_chunk_chars = max_chunk_chars
        self.languages = set(languages) if languages else None
        self._ast_fallback = AstChunker(
            chunk_size, chunk_overlap, max_chunk_chars=max_chunk_chars
        )
        self._text_fallback = TextChunker(chunk_size, chunk_overlap)

    def _detect_language(self, source_path: str) -> str | None:
        from pathlib import Path
        ext = Path(source_path).suffix.lower()
        lang = _LANGUAGE_EXTENSIONS.get(ext)
        if lang and self.languages and lang not in self.languages:
            return None
        return lang

    def chunk(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        source_path: str,
    ) -> list:
        from langchain_core.documents import Document

        language = self._detect_language(source_path)
        if not language:
            return self._text_fallback.chunk(
                text, metadata, source_path=source_path
            )

        try:
            source_bytes = text.encode("utf-8")
            symbols = _ts_extract_symbols(source_bytes, language)
        except ImportError:
            # tree-sitter not installed: fall back to ast for Python
            if language == "python":
                return self._ast_fallback.chunk(
                    text, metadata, source_path=source_path
                )
            return self._text_fallback.chunk(
                text, metadata, source_path=source_path
            )

        if not symbols:
            if language == "python":
                return self._ast_fallback.chunk(
                    text, metadata, source_path=source_path
                )
            return self._text_fallback.chunk(
                text, metadata, source_path=source_path
            )

        lines = text.splitlines(keepends=True)
        chunks: list[Document] = []
        for sym in symbols:
            start = sym["start_line"] - 1
            end = sym["end_line"]
            body = "".join(lines[start:end])

            if len(body) > self.max_chunk_chars:
                sub_meta = {**metadata, **sym, "language": language}
                sub_chunks = self._text_fallback.chunk(
                    body, sub_meta, source_path=source_path
                )
                chunks.extend(sub_chunks)
            else:
                meta = {**metadata, **sym, "language": language}
                chunks.append(Document(page_content=body, metadata=meta))

        return chunks


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

_CHUNKER_REGISTRY: dict[str, type] = {
    "text": TextChunker,
    "ast": AstChunker,
    "code": CodeChunker,
}


def get_chunker(
    name: str | None,
    *,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    options: dict[str, Any] | None = None,
) -> Chunker:
    """Return a chunker instance by name.

    Args:
        name: Backend name (text, ast, code). None defaults to "text".
        chunk_size: Default chunk size in characters.
        chunk_overlap: Default chunk overlap in characters.
        options: Extra keyword arguments forwarded to the backend constructor.
    """
    key = name or "text"
    cls = _CHUNKER_REGISTRY.get(key)
    if cls is None:
        raise ValueError(
            f"Unknown chunker {key!r}. "
            f"Available: {sorted(_CHUNKER_REGISTRY)}"
        )
    kwargs: dict[str, Any] = {
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }
    if options:
        kwargs.update(options)
    return cls(**kwargs)
