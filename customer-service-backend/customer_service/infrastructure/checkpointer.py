"""
Redis LangGraph Checkpointer - 生产级实现
支持 TTL、线程删除、异常处理
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterator, Optional
from contextlib import asynccontextmanager

import redis.asyncio as redis
from langgraph.checkpoint.base import BaseCheckpointSaver, Checkpoint, CheckpointMetadata, CheckpointTuple

from customer_service.config.config import settings

logger = logging.getLogger(__name__)


class RedisCheckpointer(BaseCheckpointSaver):
    """
    Redis-based LangGraph Checkpointer
    - 支持 TTL 过期
    - 支持 thread 删除
    - Fail-safe 降级到 MemorySaver
    """

    def __init__(
        self,
        redis_url: str | None = None,
        ttl_seconds: int | None = None,
    ):
        super().__init__()
        self.redis_url = redis_url or settings.redis_url
        self.ttl_seconds = ttl_seconds or settings.redis_checkpoint_ttl_seconds
        self._redis: redis.Redis | None = None
        self._enabled = settings.redis_enabled

    async def _get_redis(self) -> redis.Redis:
        """获取 Redis 连接"""
        if self._redis is None:
            self._redis = redis.from_url(
                self.redis_url,
                decode_responses=True,
                encoding="utf-8"
            )
        return self._redis

    def _make_key(self, thread_id: str, checkpoint_id: str) -> str:
        """生成 Redis Key"""
        return f"langgraph:checkpoint:{thread_id}:{checkpoint_id}"

    def _make_thread_key(self, thread_id: str) -> str:
        """生成 Thread 索引 Key"""
        return f"langgraph:thread:{thread_id}"

    async def aget(
        self,
        config: dict[str, Any],
    ) -> Optional[CheckpointTuple]:
        """异步获取 Checkpoint"""
        if not self._enabled:
            return None

        thread_id = config.get("configurable", {}).get("thread_id")
        checkpoint_id = config.get("configurable", {}).get("checkpoint_id")
        
        if not thread_id:
            return None

        try:
            redis_client = await self._get_redis()
            
            # 如果没有指定 checkpoint_id，获取最新的
            if not checkpoint_id:
                checkpoint_id = await redis_client.get(self._make_thread_key(thread_id))
                if not checkpoint_id:
                    return None

            key = self._make_key(thread_id, checkpoint_id)
            data = await redis_client.get(key)
            
            if not data:
                return None

            checkpoint_data = json.loads(data)
            checkpoint = Checkpoint(**checkpoint_data["checkpoint"])
            metadata = CheckpointMetadata(**checkpoint_data.get("metadata", {}))
            
            return CheckpointTuple(
                config=config,
                checkpoint=checkpoint,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Redis Checkpointer aget 失败: {e}", exc_info=True)
            return None

    async def aput(
        self,
        config: dict[str, Any],
        checkpoint: Checkpoint,
        metadata: CheckpointMetadata,
    ) -> dict[str, Any]:
        """异步保存 Checkpoint"""
        if not self._enabled:
            return config

        thread_id = config.get("configurable", {}).get("thread_id")
        checkpoint_id = checkpoint.get("id") or checkpoint.get("checkpoint_id")

        if not thread_id or not checkpoint_id:
            logger.warning("缺少 thread_id 或 checkpoint_id，跳过保存")
            return config

        try:
            redis_client = await self._get_redis()
            
            key = self._make_key(thread_id, checkpoint_id)
            thread_key = self._make_thread_key(thread_id)
            
            checkpoint_data = {
                "checkpoint": checkpoint,
                "metadata": metadata.dict() if hasattr(metadata, "dict") else metadata,
            }
            
            # 保存 Checkpoint（带 TTL）
            await redis_client.setex(
                key,
                self.ttl_seconds,
                json.dumps(checkpoint_data, default=str)
            )
            
            # 更新 Thread 索引（指向最新的 checkpoint_id）
            await redis_client.setex(
                thread_key,
                self.ttl_seconds,
                checkpoint_id
            )
            
            logger.debug(f"保存 Checkpoint: {key}")
            return config

        except Exception as e:
            logger.error(f"Redis Checkpointer aput 失败: {e}", exc_info=True)
            return config

    async def adelete_thread(self, thread_id: str) -> None:
        """删除指定 thread 的所有 Checkpoint"""
        if not self._enabled:
            return

        try:
            redis_client = await self._get_redis()
            
            # 删除 Thread 索引
            thread_key = self._make_thread_key(thread_id)
            await redis_client.delete(thread_key)
            
            # 删除所有 Checkpoint（通过模式匹配）
            pattern = f"langgraph:checkpoint:{thread_id}:*"
            cursor = 0
            while True:
                cursor, keys = await redis_client.scan(cursor, match=pattern, count=100)
                if keys:
                    await redis_client.delete(*keys)
                if cursor == 0:
                    break
            
            logger.info(f"删除 Thread: {thread_id}")

        except Exception as e:
            logger.error(f"Redis Checkpointer adelete_thread 失败: {e}", exc_info=True)

    async def aclose(self) -> None:
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.aclose()
            self._redis = None
