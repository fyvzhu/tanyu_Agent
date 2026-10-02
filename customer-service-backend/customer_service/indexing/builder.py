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
    
    async def build_index_for_product(self, product_id: str, force: bool = False) -> dict:
        """
        为单个商品构建索引（问题 #9 修复版）

        ⚠️ 重要：此方法使用 ProductKnowledgeCard，不是 ProductCard

        数据流程：
        1. 调用 commerce.knowledge_card(product_id) 获取 ProductKnowledgeCard
        2. ProductKnowledgeCard 包含稳定事实（品牌、材质、卖点），不含实时价格/库存
        3. 对 KnowledgeCard 进行文本切块和向量化
        4. 索引到 Qdrant 和 Elasticsearch

        问题 #9 修复：
        - 使用稳定的 UUID5 chunk ID
        - 增量更新：删除旧 chunks，只保留新 chunks
        - 两阶段同步验证：分别验证 Qdrant 和 ES 写入成功
        - 返回详细状态：built/skipped/failed

        Args:
            product_id: 商品 ID
            force: 是否强制重建（忽略 manifest）

        Returns:
            构建结果字典: {"status": "built"|"skipped"|"failed", "chunks": int, "error": str|None}
        """
        logger.info(f"[{product_id}] 🚀 开始构建索引，force={force}")

        source_hash = ""
        index_signature = ""

        try:
            # 1. 获取商品知识卡片
            # ⚠️ 注意：这里获取的是 ProductKnowledgeCard，不是 ProductCard
            knowledge_card = await self.commerce.knowledge_card(product_id)
            if not knowledge_card:
                logger.warning(f"[{product_id}] ⚠️ 商品不存在或无知识卡片")
                return {"status": "failed", "chunks": 0, "error": "商品不存在或无知识卡片"}

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
                    return {"status": "skipped", "chunks": 0, "error": None}

            # 5. 获取旧的 chunk IDs（用于后续清理）
            old_chunk_ids = await self._get_existing_chunk_ids(product_id)
            logger.info(f"[{product_id}] 📋 现有 chunks: {len(old_chunk_ids)} 个")

            # 6. 切分为 chunks
            chunks = self.chunker.chunk_product(product_id, knowledge_card)
            logger.info(f"[{product_id}] 📦 切分为 {len(chunks)} 个 chunks")

            # 7. 生成 embeddings
            texts = [chunk.text for chunk in chunks]
            vectors = await self.embedder.embed_batch(texts)
            logger.info(f"[{product_id}] 🔢 生成 {len(vectors)} 个向量")

            # 8. 准备 chunk payloads
            chunk_payloads = []
            new_chunk_ids = set()
            for chunk, vector in zip(chunks, vectors):
                new_chunk_ids.add(chunk.chunk_id)
                chunk_payloads.append({
                    "chunk_id": chunk.chunk_id,
                    "logical_id": chunk.logical_id,
                    "product_id": chunk.product_id,
                    "chunk_type": chunk.chunk_type,
                    "text": chunk.text,
                    "vector": vector,
                    "brand": chunk.metadata.get("brand"),
                    "category": chunk.metadata.get("category"),
                    "source_hash": source_hash,
                    "index_signature": index_signature,
                })

            # 9. 计算需要删除的旧 chunks
            chunks_to_delete = old_chunk_ids - new_chunk_ids
            if chunks_to_delete:
                logger.info(f"[{product_id}] 🗑️  将删除 {len(chunks_to_delete)} 个旧 chunks")

            # 10. 两阶段写入：Qdrant
            qdrant_success = False
            try:
                await self.qdrant.upsert_chunks(chunk_payloads)
                logger.info(f"[{product_id}] 💾 Qdrant 写入成功")
                qdrant_success = True
            except Exception as e:
                logger.error(f"[{product_id}] ❌ Qdrant 写入失败: {e}")

            # 11. 两阶段写入：Elasticsearch
            es_success = False
            try:
                await self.es.bulk_index_chunks(chunk_payloads)
                logger.info(f"[{product_id}] 💾 Elasticsearch 写入成功")
                es_success = True
            except Exception as e:
                logger.error(f"[{product_id}] ❌ Elasticsearch 写入失败: {e}")

            # 12. 删除旧 chunks（仅在两边都成功时）
            if chunks_to_delete and qdrant_success and es_success:
                try:
                    await self.qdrant.delete_chunks(list(chunks_to_delete))
                    await self.es.delete_chunks(list(chunks_to_delete))
                    logger.info(f"[{product_id}] 🗑️  旧 chunks 清理完成")
                except Exception as e:
                    logger.warning(f"[{product_id}] ⚠️  旧 chunks 清理失败: {e}")

            # 13. 确定同步状态
            if qdrant_success and es_success:
                sync_status = "synced"
            elif qdrant_success or es_success:
                sync_status = "partial"
            else:
                sync_status = "failed"

            # 14. 更新 manifest
            await update_manifest(
                self.db,
                product_id,
                {
                    "source_hash": source_hash,
                    "index_signature": index_signature,
                    "chunk_count": len(chunks),
                    "qdrant_sync_status": "synced" if qdrant_success else "failed",
                    "es_sync_status": "synced" if es_success else "failed",
                    "indexed_at": datetime.utcnow(),
                    "last_error": None if (qdrant_success and es_success) else f"qdrant={qdrant_success}, es={es_success}",
                }
            )

            if sync_status == "synced":
                logger.info(f"[{product_id}] ✅ 索引构建成功")
                return {"status": "built", "chunks": len(chunks), "error": None}
            elif sync_status == "partial":
                logger.warning(f"[{product_id}] ⚠️  索引部分成功 (Qdrant={qdrant_success}, ES={es_success})")
                return {"status": "failed", "chunks": len(chunks), "error": f"部分同步失败: Qdrant={qdrant_success}, ES={es_success}"}
            else:
                logger.error(f"[{product_id}] ❌ 索引构建失败（两边都失败）")
                return {"status": "failed", "chunks": 0, "error": "Qdrant 和 ES 写入都失败"}

        except Exception as e:
            logger.exception(f"[{product_id}] ❌ 索引构建异常: {e}")

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
            return {"status": "failed", "chunks": 0, "error": str(e)[:200]}

    async def _get_existing_chunk_ids(self, product_id: str) -> set[str]:
        """
        获取商品的现有 chunk IDs

        Args:
            product_id: 商品 ID

        Returns:
            chunk_id 集合
        """
        try:
            # 从 Qdrant 查询现有 chunks
            existing_chunks = await self.qdrant.get_chunks_by_product(product_id)
            return {chunk["chunk_id"] for chunk in existing_chunks}
        except Exception as e:
            logger.warning(f"[{product_id}] 获取现有 chunks 失败: {e}")
            return set()

    async def build_index_batch(self, product_ids: list[str], force: bool = False) -> dict:
        """
        批量构建索引（问题 #9 修复版）

        Args:
            product_ids: 商品 ID 列表
            force: 是否强制重建

        Returns:
            构建结果统计: {"built": int, "skipped": int, "failed": int, "details": list}
        """
        results = {"built": 0, "skipped": 0, "failed": 0, "details": []}

        logger.info(f"📦 开始批量构建索引，共 {len(product_ids)} 个商品")

        for i, product_id in enumerate(product_ids, 1):
            logger.info(f"[{i}/{len(product_ids)}] 处理商品 {product_id}")
            result = await self.build_index_for_product(product_id, force=force)

            status = result["status"]
            if status == "built":
                results["built"] += 1
            elif status == "skipped":
                results["skipped"] += 1
            else:  # failed
                results["failed"] += 1

            results["details"].append({
                "product_id": product_id,
                "status": status,
                "chunks": result["chunks"],
                "error": result["error"]
            })

        logger.info(f"✅ 批量索引完成: built={results['built']}, skipped={results['skipped']}, failed={results['failed']}")
        return results
