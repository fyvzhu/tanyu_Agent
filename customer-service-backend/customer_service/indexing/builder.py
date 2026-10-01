"""
商品索引构建器

提供单个商品和批量商品的索引构建功能
"""
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.infrastructure.embedding import EmbeddingClient
from customer_service.indexing.chunker import ProductChunker
from customer_service.indexing.manifest import (
    compute_source_hash,
    compute_index_signature,
    should_reindex,
    update_manifest,
)
from customer_service.retrieval.service import QdrantProductRetriever, ElasticsearchProductRetriever


class ProductIndexBuilder:
    """商品索引构建器"""
    
    def __init__(
        self,
        db_session: AsyncSession,
        ecommerce_client: EcommerceClient,
        embedding_client: EmbeddingClient,
        qdrant_retriever: QdrantProductRetriever,
        es_retriever: ElasticsearchProductRetriever,
    ):
        self.db = db_session
        self.commerce = ecommerce_client
        self.embedder = embedding_client
        self.qdrant = qdrant_retriever
        self.es = es_retriever
        self.chunker = ProductChunker()
    
    async def build_index_for_product(self, product_id: str, force: bool = False) -> bool:
        """
        为单个商品构建索引
        
        Args:
            product_id: 商品 ID
            force: 是否强制重建（忽略 manifest）
        
        Returns:
            是否成功构建
        """
        logger.info(f"[{product_id}] 🚀 开始构建索引，force={force}")
        
        source_hash = ""
        index_signature = ""
        
        try:
            # 1. 获取商品知识卡片
            knowledge_card = await self.commerce.knowledge_card(product_id)
            if not knowledge_card:
                logger.warning(f"[{product_id}] ⚠️ 商品不存在或无知识卡片")
                return False
            
            # 2. 计算 source_hash
            source_hash = compute_source_hash(knowledge_card)
            
            # 3. 计算 index_signature
            index_signature = compute_index_signature(
                source_hash=source_hash,
                schema_version="v1",
                chunker_version=self.chunker.CHUNKER_VERSION,
                embedding_model="BAAI/bge-m3",
                embedding_dimension=1024,
            )
            
            # 4. 判断是否需要重建
            if not force:
                needs_rebuild = await should_reindex(
                    self.db,
                    product_id,
                    source_hash,
                    index_signature,
                )
                if not needs_rebuild:
                    logger.info(f"[{product_id}] ✅ 索引已是最新，跳过")
                    return True
            
            # 5. 切分为 chunks
            chunks = self.chunker.chunk_product(product_id, knowledge_card)
            logger.info(f"[{product_id}] 📦 切分为 {len(chunks)} 个 chunks")
            
            # 6. 生成 embeddings
            texts = [chunk.text for chunk in chunks]
            vectors = await self.embedder.embed_batch(texts)
            logger.info(f"[{product_id}] 🔢 生成 {len(vectors)} 个向量")
            
            # 7. 准备 chunk payloads
            chunk_payloads = []
            for chunk, vector in zip(chunks, vectors):
                chunk_payloads.append({
                    "chunk_id": chunk.chunk_id,
                    "product_id": chunk.product_id,
                    "chunk_type": chunk.chunk_type,
                    "text": chunk.text,
                    "vector": vector,
                    "brand": chunk.metadata.get("brand"),
                    "category": chunk.metadata.get("category"),
                    "source_hash": source_hash,
                    "index_signature": index_signature,
                })
            
            # 8. 写入 Qdrant
            await self.qdrant.upsert_chunks(chunk_payloads)
            logger.info(f"[{product_id}] 💾 写入 Qdrant 完成")
            
            # 9. 写入 Elasticsearch
            await self.es.bulk_index_chunks(chunk_payloads)
            logger.info(f"[{product_id}] 💾 写入 Elasticsearch 完成")
            
            # 10. 更新 manifest
            await update_manifest(
                self.db,
                product_id,
                {
                    "source_hash": source_hash,
                    "index_signature": index_signature,
                    "chunk_count": len(chunks),
                    "qdrant_sync_status": "synced",
                    "es_sync_status": "synced",
                    "indexed_at": datetime.utcnow(),
                    "last_error": None,
                }
            )
            
            logger.info(f"[{product_id}] ✅ 索引构建成功")
            return True
        
        except Exception as e:
            logger.exception(f"[{product_id}] ❌ 索引构建失败: {e}")

            # 记录错误到 manifest
            await update_manifest(
                self.db,
                product_id,
                {
                    "source_hash": source_hash,
                    "index_signature": index_signature,
                    "chunk_count": 0,
                    "qdrant_sync_status": "failed",
                    "es_sync_status": "failed",
                    "indexed_at": datetime.utcnow(),
                    "last_error": str(e)[:500],
                }
            )
            return False

    async def build_index_batch(self, product_ids: list[str], force: bool = False) -> dict:
        """
        批量构建索引

        Args:
            product_ids: 商品 ID 列表
            force: 是否强制重建

        Returns:
            构建结果统计: {"success": int, "failed": int, "skipped": int}
        """
        results = {"success": 0, "failed": 0, "skipped": 0}

        logger.info(f"📦 开始批量构建索引，共 {len(product_ids)} 个商品")

        for i, product_id in enumerate(product_ids, 1):
            logger.info(f"[{i}/{len(product_ids)}] 处理商品 {product_id}")
            success = await self.build_index_for_product(product_id, force=force)
            if success:
                results["success"] += 1
            else:
                results["failed"] += 1

        logger.info(f"✅ 批量索引完成: {results}")
        return results
