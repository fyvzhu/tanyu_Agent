"""
商品索引管理模块

提供商品数据索引、签名计算、同步状态管理和文本切分功能
"""
from customer_service.indexing.manifest import (
    compute_source_hash,
    compute_index_signature,
    should_reindex,
    update_manifest,
    get_manifest,
)
from customer_service.indexing.chunker import ProductChunker, ProductChunk, ChunkType

__all__ = [
    "compute_source_hash",
    "compute_index_signature",
    "should_reindex",
    "update_manifest",
    "get_manifest",
    "ProductChunker",
    "ProductChunk",
    "ChunkType",
]
