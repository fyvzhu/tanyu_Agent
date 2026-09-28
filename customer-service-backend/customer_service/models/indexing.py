"""
商品索引清单 ORM 模型

用于追踪商品数据的索引状态和同步状态
"""
from datetime import datetime
from sqlalchemy import Column, String, Integer, DateTime, Text
from customer_service.models.base import Base


class ProductIndexManifest(Base):
    """
    商品索引清单模型
    
    记录每个商品的索引状态，包括：
    - 商品原始数据的哈希值（用于判断数据是否变化）
    - 索引配置签名（用于判断索引配置是否变化）
    - 向量数据库和搜索引擎的同步状态
    - chunk 数量和错误信息
    """
    __tablename__ = "product_index_manifest"
    
    # 主键：商品 ID
    product_id = Column(
        String(50), 
        primary_key=True,
        comment="商品 ID"
    )
    
    # 商品原始数据的哈希值
    source_hash = Column(
        String(64), 
        nullable=False,
        comment="商品原始数据的 SHA256 哈希"
    )
    
    # 索引配置签名
    index_signature = Column(
        String(128), 
        nullable=False,
        comment="索引配置签名（包含 embedding model, chunker version 等）"
    )
    
    # chunk 数量
    chunk_count = Column(
        Integer, 
        default=0,
        nullable=False,
        comment="该商品的 chunk 数量"
    )
    
    # Qdrant 同步状态
    qdrant_sync_status = Column(
        String(20), 
        default="pending",
        nullable=False,
        comment="Qdrant 同步状态: pending/synced/failed"
    )
    
    # Elasticsearch 同步状态
    es_sync_status = Column(
        String(20), 
        default="pending",
        nullable=False,
        comment="Elasticsearch 同步状态: pending/synced/failed"
    )
    
    # 索引时间
    indexed_at = Column(
        DateTime, 
        nullable=False,
        default=datetime.utcnow,
        comment="索引时间"
    )
    
    # 最后一次错误信息
    last_error = Column(
        Text, 
        nullable=True,
        comment="最后一次同步错误信息"
    )
    
    def __repr__(self) -> str:
        return (
            f"<ProductIndexManifest("
            f"product_id={self.product_id!r}, "
            f"qdrant={self.qdrant_sync_status!r}, "
            f"es={self.es_sync_status!r}, "
            f"chunks={self.chunk_count})>"
        )
    
    def is_synced(self) -> bool:
        """检查是否完全同步"""
        return (
            self.qdrant_sync_status == "synced" and 
            self.es_sync_status == "synced"
        )
    
    def has_error(self) -> bool:
        """检查是否有同步错误"""
        return (
            self.qdrant_sync_status == "failed" or 
            self.es_sync_status == "failed"
        )
