"""
商品索引清单管理模块

提供商品数据哈希计算、索引签名生成、重建索引判断和清单更新功能
"""
import hashlib
import json
from datetime import datetime
from typing import Optional, Dict, Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from customer_service.models.indexing import ProductIndexManifest


def compute_source_hash(product_data: dict) -> str:
    """
    计算商品数据的 SHA256 哈希

    只包含影响索引的字段，确保哈希值稳定且有意义

    P1-43 修复：包含 size_summary 字段，因为 Chunker 会为它创建 chunk

    Args:
        product_data: 商品数据字典

    Returns:
        64 字符的十六进制 SHA256 哈希值

    Example:
        >>> data = {"product_id": "15970", "brand": "Nike", ...}
        >>> compute_source_hash(data)
        'a3f5b8c9d2e1f4a7b6c5d8e9f2a1b4c7d8e9f2a3b4c5d6e7f8a9b0c1d2e3f4a5'
    """
    # P1-43: 包含所有会影响索引文本的字段
    stable_fields = {
        "product_id": product_data.get("product_id"),
        "brand": product_data.get("brand"),
        "product_display_name": product_data.get("product_display_name"),
        "category": product_data.get("category"),
        "material": product_data.get("material"),
        "selling_points": product_data.get("selling_points"),
        "features": product_data.get("features"),
        "size_summary": product_data.get("size_summary"),  # P1-43: 包含尺码摘要
    }

    # 使用 sort_keys=True 确保顺序一致，ensure_ascii=False 支持中文
    canonical = json.dumps(stable_fields, sort_keys=True, ensure_ascii=False)
    hash_value = hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    logger.debug(
        f"计算商品 {product_data.get('product_id')} 的源数据哈希: {hash_value[:16]}..."
    )

    return hash_value


def compute_index_signature(
    source_hash: str,
    schema_version: str = "v1",
    chunker_version: str = "v1",
    embedding_model: str = "BAAI/bge-m3",
    embedding_dimension: int = 1024,
) -> str:
    """
    计算索引配置签名
    
    当索引配置（embedding 模型、chunker 版本等）变化时，签名也会变化，
    触发索引重建
    
    Args:
        source_hash: 商品数据的哈希值
        schema_version: Schema 版本
        chunker_version: Chunker 版本
        embedding_model: Embedding 模型名称
        embedding_dimension: Embedding 维度
        
    Returns:
        32 字符的索引签名（SHA256 前 32 位）
        
    Example:
        >>> compute_index_signature("abc123", "v1", "v1", "BAAI/bge-m3", 1024)
        'f4a7b6c5d8e9f2a1b4c7d8e9f2a3b4c5'
    """
    # 组合所有影响索引的配置参数
    sig_input = (
        f"{source_hash}:"
        f"{schema_version}:"
        f"{chunker_version}:"
        f"{embedding_model}:"
        f"{embedding_dimension}"
    )
    
    # 计算 SHA256 并取前 32 位作为签名
    signature = hashlib.sha256(sig_input.encode('utf-8')).hexdigest()[:32]
    
    logger.debug(f"计算索引签名: {signature}")
    
    return signature


async def should_reindex(
    db: AsyncSession,
    product_id: str,
    current_hash: str,
    current_signature: str
) -> bool:
    """
    判断商品是否需要重建索引

    在以下情况下需要重建：
    1. 清单中不存在该商品记录
    2. 商品数据发生变化（source_hash 不同）
    3. 索引配置发生变化（index_signature 不同）

    Args:
        db: 异步数据库会话
        product_id: 商品 ID
        current_hash: 当前商品数据的哈希值
        current_signature: 当前索引配置的签名

    Returns:
        True 表示需要重建索引，False 表示不需要
    """
    result = await db.execute(
        select(ProductIndexManifest).filter(
            ProductIndexManifest.product_id == product_id
        )
    )
    manifest = result.scalar_one_or_none()

    # 情况 1: 清单中不存在，需要建立索引
    if manifest is None:
        logger.info(f"商品 {product_id} 无索引记录，需要建立索引")
        return True

    # 情况 2: 商品数据发生变化
    if manifest.source_hash != current_hash:
        logger.info(
            f"商品 {product_id} 数据已变化 "
            f"(旧哈希: {manifest.source_hash[:16]}..., "
            f"新哈希: {current_hash[:16]}...)，需要重建索引"
        )
        return True

    # 情况 3: 索引配置发生变化
    if manifest.index_signature != current_signature:
        logger.info(
            f"商品 {product_id} 索引配置已变化 "
            f"(旧签名: {manifest.index_signature}, "
            f"新签名: {current_signature})，需要重建索引"
        )
        return True

    logger.debug(f"商品 {product_id} 索引无需更新")
    return False


async def update_manifest(
    db: AsyncSession,
    product_id: str,
    manifest_data: Dict[str, Any]
) -> ProductIndexManifest:
    """
    更新或创建商品索引清单记录

    Args:
        db: 异步数据库会话
        product_id: 商品 ID
        manifest_data: 清单数据，包含以下字段：
            - source_hash: 商品数据哈希
            - index_signature: 索引签名
            - chunk_count: chunk 数量
            - qdrant_sync_status: Qdrant 同步状态（可选，默认 'pending'）
            - es_sync_status: ES 同步状态（可选，默认 'pending'）
            - last_error: 错误信息（可选）

    Returns:
        更新后的 ProductIndexManifest 实例
    """
    result = await db.execute(
        select(ProductIndexManifest).filter(
            ProductIndexManifest.product_id == product_id
        )
    )
    manifest = result.scalar_one_or_none()

    if manifest is None:
        # 创建新记录
        manifest = ProductIndexManifest(
            product_id=product_id,
            source_hash=manifest_data["source_hash"],
            index_signature=manifest_data["index_signature"],
            chunk_count=manifest_data.get("chunk_count", 0),
            qdrant_sync_status=manifest_data.get("qdrant_sync_status", "pending"),
            es_sync_status=manifest_data.get("es_sync_status", "pending"),
            indexed_at=datetime.utcnow(),
            last_error=manifest_data.get("last_error"),
        )
        db.add(manifest)
        logger.info(f"创建商品 {product_id} 的索引清单记录")
    else:
        # 更新现有记录
        manifest.source_hash = manifest_data["source_hash"]
        manifest.index_signature = manifest_data["index_signature"]
        manifest.chunk_count = manifest_data.get("chunk_count", manifest.chunk_count)
        manifest.qdrant_sync_status = manifest_data.get(
            "qdrant_sync_status", manifest.qdrant_sync_status
        )
        manifest.es_sync_status = manifest_data.get(
            "es_sync_status", manifest.es_sync_status
        )
        manifest.indexed_at = datetime.utcnow()
        manifest.last_error = manifest_data.get("last_error")
        logger.info(f"更新商品 {product_id} 的索引清单记录")

    await db.commit()
    await db.refresh(manifest)

    return manifest


async def get_manifest(
    db: AsyncSession,
    product_id: str
) -> Optional[ProductIndexManifest]:
    """
    获取商品的索引清单记录

    Args:
        db: 异步数据库会话
        product_id: 商品 ID

    Returns:
        ProductIndexManifest 实例，如果不存在则返回 None
    """
    result = await db.execute(
        select(ProductIndexManifest).filter(
            ProductIndexManifest.product_id == product_id
        )
    )
    manifest = result.scalar_one_or_none()

    if manifest:
        logger.debug(f"找到商品 {product_id} 的索引清单记录")
    else:
        logger.debug(f"商品 {product_id} 无索引清单记录")

    return manifest
