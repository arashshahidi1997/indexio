"""indexio — lightweight semantic indexing and retrieval for project knowledge sources."""

from .config import IndexioConfig, StoreConfig, SourceConfig, load_indexio_config
from .build import build_index, sync_owned_sources
from .query import query_index, query_index_multi

__all__ = [
    "IndexioConfig",
    "StoreConfig",
    "SourceConfig",
    "load_indexio_config",
    "build_index",
    "sync_owned_sources",
    "query_index",
    "query_index_multi",
]
