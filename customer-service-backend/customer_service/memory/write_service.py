"""
Memory Write Service - 完整的记忆写入管道
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from customer_service.memory.extractor import MemoryCandidateExtractor
from customer_service.memory.conflict_resolver import ConflictResolver, ConflictResolution
from customer_service.memory.long_term import LongTermProvider
from customer_service.memory.semantic_memory import SemanticProvider
from customer_service.memory.schemas import MemoryFact, MemoryEvent

logger = logging.getLogger(__name__)


class MemoryWriteService:
    """
    完整的记忆写入管道
    
    遵循文档 4.19 节流程：
    current user message + confirmed tool facts
    → MemoryCandidateExtractor
    → durable-fact whitelist
    → PII / secret filter
    → Qdrant related memories Top-K
    → ConflictResolver (duplicate/update/new/uncertain)
    → memory_events audit
    """
    
    # PII / Secret 关键词黑名单
    PII_KEYWORDS = [
        "密码", "password", "验证码", "token", "身份证", "银行卡",
        "手机号", "电话", "邮箱", "email", "地址", "家庭住址",
    ]
    
    def __init__(
        self,
        extractor: MemoryCandidateExtractor,
        resolver: ConflictResolver,
        long_term_provider: LongTermProvider,
        semantic_provider: SemanticProvider,
        embedder,  # 向量化服务
    ):
        self.extractor = extractor
        self.resolver = resolver
        self.long_term_provider = long_term_provider
        self.semantic_provider = semantic_provider
        self.embedder = embedder
    
    async def process_turn(
        self,
        user_id: str,
        session_id: str,
        turn_id: str,
        user_message: str,
        tool_result: dict | None = None,
    ) -> dict:
        """
        处理一轮对话的记忆写入
        
        Returns:
            处理统计信息
        """
        stats = {
            "extracted": 0,
            "filtered_pii": 0,
            "skipped": 0,
            "new": 0,
            "updated": 0,
            "superseded": 0,
            "uncertain": 0,
        }
        
        # 1. 提取候选记忆
        candidates = self.extractor.extract_from_conversation(
            user_id=user_id,
            session_id=session_id,
            turn_id=turn_id,
            user_message=user_message,
            tool_result=tool_result,
        )
        stats["extracted"] = len(candidates)
        
        if not candidates:
            return stats
        
        # 2. PII / Secret 过滤
        filtered_candidates = []
        for candidate in candidates:
            if self._contains_pii(candidate.memory_text):
                stats["filtered_pii"] += 1
                logger.warning(f"Filtered PII memory: {candidate.memory_key}")
                continue
            filtered_candidates.append(candidate)
        
        # 3. 获取相关的已存在记忆（从 MySQL）
        existing_memories = await self.long_term_provider.get_facts(user_id, limit=100)
        
        # 4. 逐个解决冲突并写入
        for candidate in filtered_candidates:
            try:
                # 4.1 解决冲突
                resolution, target_memory = self.resolver.resolve(candidate, existing_memories)
                
                # 4.2 根据策略执行
                if resolution == ConflictResolution.SKIP:
                    stats["skipped"] += 1
                    continue
                
                elif resolution == ConflictResolution.NEW:
                    # 新增记忆
                    await self._add_new_memory(candidate)
                    stats["new"] += 1
                
                elif resolution == ConflictResolution.UPDATE:
                    # 更新记忆
                    if target_memory:
                        await self._update_memory(target_memory.memory_id, candidate)
                        stats["updated"] += 1
                
                elif resolution == ConflictResolution.SUPERSEDE:
                    # 替换记忆
                    if target_memory:
                        await self._supersede_memory(target_memory.memory_id, candidate)
                        stats["superseded"] += 1
                
                elif resolution == ConflictResolution.UNCERTAIN:
                    # 不持久化，只记录统计
                    stats["uncertain"] += 1
                    logger.info(f"Uncertain memory not persisted: {candidate.memory_key}")
            
            except Exception as e:
                logger.error(f"Failed to process memory {candidate.memory_key}: {e}")
        
        return stats
    
    async def _add_new_memory(self, fact: MemoryFact) -> bool:
        """添加新记忆"""
        try:
            # 1. 写入 MySQL
            success = await self.long_term_provider.add_fact(fact)
            if not success:
                return False
            
            # 2. 向量化并写入 Qdrant
            embedding = await self.embedder.embed(fact.memory_text)
            await self.semantic_provider.add_memory(fact, embedding)
            
            # 3. 记录事件
            event = MemoryEvent(
                memory_id=fact.memory_id,
                action="created",
                old_value_json=None,
                new_value_json=fact.value_json,
                source_turn_id=fact.source_turn_id,
                created_at=datetime.now(timezone.utc),
            )
            await self.long_term_provider.add_event(event)
            
            logger.info(f"Added new memory: {fact.memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to add new memory: {e}")
            return False
    
    async def _update_memory(self, memory_id: str, updated_fact: MemoryFact) -> bool:
        """更新记忆"""
        try:
            # 1. 更新 MySQL
            success = await self.long_term_provider.update_fact(memory_id, updated_fact)
            if not success:
                return False
            
            # 2. 更新 Qdrant
            embedding = await self.embedder.embed(updated_fact.memory_text)
            await self.semantic_provider.update_memory(memory_id, updated_fact, embedding)
            
            logger.info(f"Updated memory: {memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to update memory: {e}")
            return False
    
    async def _supersede_memory(self, old_memory_id: str, new_fact: MemoryFact) -> bool:
        """替换记忆（标记旧的为 superseded，插入新的）"""
        try:
            # 1. MySQL 中标记旧记忆并插入新记忆
            success = await self.long_term_provider.supersede_fact(old_memory_id, new_fact)
            if not success:
                return False
            
            # 2. Qdrant 中标记旧记忆为 deleted，插入新记忆
            await self.semantic_provider.delete_memory(old_memory_id)
            embedding = await self.embedder.embed(new_fact.memory_text)
            await self.semantic_provider.add_memory(new_fact, embedding)
            
            logger.info(f"Superseded memory: {old_memory_id} -> {new_fact.memory_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to supersede memory: {e}")
            return False
    
    def _contains_pii(self, text: str) -> bool:
        """检查是否包含 PII/敏感信息"""
        text_lower = text.lower()
        return any(kw in text_lower for kw in self.PII_KEYWORDS)
