"""indexio — lightweight semantic indexing and retrieval for project knowledge sources."""

from .config import IndexioConfig, StoreConfig, SourceConfig, load_indexio_config
from .build import build_index, sync_owned_sources
from .chunkers import get_chunker
from .graph import CodeGraph, build_file_graph, build_project_graph
from .query import query_index, query_index_multi

__all__ = [
    "IndexioConfig",
    "StoreConfig",
    "SourceConfig",
    "load_indexio_config",
    "build_index",
    "sync_owned_sources",
    "get_chunker",
    "CodeGraph",
    "build_file_graph",
    "build_project_graph",
    "query_index",
    "query_index_multi",
]
