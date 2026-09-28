"""
Qdrant 语义记忆 Provider
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Protocol

from customer_service.memory.schemas import MemoryFact, SemanticMemoryPayload

logger = logging.getLogger(__name__)


class SemanticProvider(Protocol):
    """语义记忆 Provider 接口"""

    async def add_memory(self, fact: MemoryFact, embedding: list[float]) -> bool:
        """添加语义记忆到向量库"""
        ...

    async def search(
        self, query_embedding: list[float], user_id: str, limit: int = 5
    ) -> list[dict]:
        """语义检索"""
        ...

    async def update_memory(
        self, memory_id: str, fact: MemoryFact, embedding: list[float]
    ) -> bool:
        """更新语义记忆"""
        ...

    async def delete_memory(self, memory_id: str) -> bool:
        """删除语义记忆"""
        ...


class QdrantSemanticProvider:
    """
    Qdrant 语义记忆实现
    
    Collection: user_memory
    Payload 结构:
    {
      "memory_id": "MEM-U0001-000123",
      "user_id": "U0001",
      "memory_type": "preference",
      "memory_key": "preferred_color",
      "memory_text": "用户购买通勤服装时更偏好黑色和藏青色",
      "importance": 0.82,
      "confidence": 0.90,
      "source_session_id": "S...",
      "source_turn_id": "T...",
      "status": "active",
      "created_at": "...",
      "expires_at": null
    }
    
    必须给 user_id、status 建 payload index，检索时强制过滤:
    user_id == authenticated_user_id AND status == active
    """

    def __init__(self, qdrant_client, collection_name: str = "user_memory"):
        """
        Args:
            qdrant_client: Qdrant 客户端实例
            collection_name: 集合名称
        """
        self.client = qdrant_client
        self.collection_name = collection_name

    async def ensure_collection(self, vector_size: int = 1024):
        """确保 collection 存在并创建索引"""
        try:
            from qdrant_client.models import Distance, VectorParams, PayloadSchemaType

            # 创建 collection（如果不存在）
            collections = await self.client.get_collections()
            if self.collection_name not in [c.name for c in collections.collections]:
                await self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE),
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")

            # 创建 payload 索引（user_id 和 status 必须索引）
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="user_id",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            await self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="status",
                field_schema=PayloadSchemaType.KEYWORD,
            )
            logger.info(f"Ensured payload indexes on user_id and status")
            return True
        except Exception as e:
            logger.error(f"Failed to ensure Qdrant collection: {e}")
            return False

    async def add_memory(self, fact: MemoryFact, embedding: list[float]) -> bool:
        """添加语义记忆到向量库"""
        try:
            from qdrant_client.models import PointStruct

            payload = SemanticMemoryPayload(
                memory_id=fact.memory_id,
                user_id=fact.user_id,
                memory_type=fact.memory_type.value,
                memory_key=fact.memory_key,
                memory_text=fact.memory_text,
                importance=fact.importance,
                confidence=fact.confidence,
                source_session_id=fact.source_session_id,
                source_turn_id=fact.source_turn_id,
                status=fact.status.value,
                created_at=fact.created_at.isoformat(),
                expires_at=fact.expires_at.isoformat() if fact.expires_at else None,
            )

            point = PointStruct(
                id=fact.memory_id,  # 使用 memory_id 作为 point id
                vector=embedding,
                payload=payload.model_dump(),
            )

            await self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
            logger.info(f"Added semantic memory: {fact.memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add semantic memory: {e}")
            return False

    async def search(
        self, query_embedding: list[float], user_id: str, limit: int = 5
    ) -> list[dict]:
        """
        语义检索，强制过滤 user_id 和 status
        """
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # 强制过滤：user_id == authenticated_user_id AND status == active
            search_filter = Filter(
                must=[
                    FieldCondition(key="user_id", match=MatchValue(value=user_id)),
                    FieldCondition(key="status", match=MatchValue(value="active")),
                ]
            )

            results = await self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=search_filter,
                limit=limit,
            )

            memories = []
            for result in results:
                memories.append({
                    "memory_id": result.payload.get("memory_id"),
                    "memory_text": result.payload.get("memory_text"),
                    "memory_type": result.payload.get("memory_type"),
                    "importance": result.payload.get("importance"),
                    "confidence": result.payload.get("confidence"),
                    "score": result.score,
                })
            return memories
        except Exception as e:
            logger.error(f"Failed to search semantic memories: {e}")
            return []

    async def update_memory(
        self, memory_id: str, fact: MemoryFact, embedding: list[float]
    ) -> bool:
        """更新语义记忆（实际是 upsert）"""
        try:
            from qdrant_client.models import PointStruct

            payload = SemanticMemoryPayload(
                memory_id=fact.memory_id,
                user_id=fact.user_id,
                memory_type=fact.memory_type.value,
                memory_key=fact.memory_key,
                memory_text=fact.memory_text,
                importance=fact.importance,
                confidence=fact.confidence,
                source_session_id=fact.source_session_id,
                source_turn_id=fact.source_turn_id,
                status=fact.status.value,
                created_at=fact.created_at.isoformat(),
                expires_at=fact.expires_at.isoformat() if fact.expires_at else None,
            )

            point = PointStruct(
                id=memory_id,
                vector=embedding,
                payload=payload.model_dump(),
            )

            await self.client.upsert(
                collection_name=self.collection_name,
                points=[point],
            )
            logger.info(f"Updated semantic memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update semantic memory: {e}")
            return False

    async def delete_memory(self, memory_id: str) -> bool:
        """删除语义记忆（实际是标记 status 为 deleted）"""
        try:
            from qdrant_client.models import Filter, FieldCondition, MatchValue

            # 方案1：直接删除 point
            # await self.client.delete(
            #     collection_name=self.collection_name,
            #     points_selector=[memory_id],
            # )

            # 方案2：更新 payload status（推荐，保留审计）
            await self.client.set_payload(
                collection_name=self.collection_name,
                payload={"status": "deleted"},
                points=[memory_id],
            )

            logger.info(f"Deleted semantic memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to delete semantic memory: {e}")
            return False
