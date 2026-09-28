"""
Memory Conflict Resolver - 处理记忆冲突和去重
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum

from customer_service.memory.schemas import MemoryFact, MemoryStatus

logger = logging.getLogger(__name__)


class ConflictResolution(str, Enum):
    """冲突解决策略"""
    SKIP = "skip"              # 跳过（重复）
    UPDATE = "update"          # 更新现有记忆
    NEW = "new"                # 添加新记忆
    SUPERSEDE = "supersede"    # 替换旧记忆
    UNCERTAIN = "uncertain"    # 不确定，只存 Redis


class ConflictResolver:
    """
    记忆冲突解决器
    
    遵循文档 4.19 节要求：
    - duplicate → skip
    - update → Agent MySQL update + Qdrant upsert
    - new → Agent MySQL insert + Qdrant upsert
    - uncertain → only Redis / do not persist
    """
    
    def __init__(self, similarity_threshold: float = 0.85):
        """
        Args:
            similarity_threshold: 相似度阈值，超过此值认为是重复
        """
        self.similarity_threshold = similarity_threshold
    
    def resolve(
        self,
        candidate: MemoryFact,
        existing_memories: list[MemoryFact],
    ) -> tuple[ConflictResolution, MemoryFact | None]:
        """
        解决记忆冲突
        
        Args:
            candidate: 候选记忆
            existing_memories: 已存在的记忆列表
        
        Returns:
            (解决策略, 目标记忆)
        """
        # 1. 检查是否有相同 memory_key 的记忆
        same_key_memories = [
            m for m in existing_memories
            if m.memory_key == candidate.memory_key and m.status == MemoryStatus.ACTIVE
        ]
        
        if not same_key_memories:
            # 没有冲突，直接添加
            return ConflictResolution.NEW, candidate
        
        # 2. 检查内容是否重复
        for existing in same_key_memories:
            if self._is_duplicate(candidate, existing):
                logger.info(f"Duplicate memory detected: {candidate.memory_key}")
                return ConflictResolution.SKIP, None
        
        # 3. 检查是否需要更新
        most_recent = max(same_key_memories, key=lambda m: m.created_at)
        
        # 如果候选记忆的置信度更高，替换旧记忆
        if candidate.confidence > most_recent.confidence + 0.1:
            logger.info(f"Superseding memory: {candidate.memory_key} (old conf={most_recent.confidence}, new conf={candidate.confidence})")
            return ConflictResolution.SUPERSEDE, most_recent
        
        # 如果候选记忆的置信度相近但内容不同，更新
        if abs(candidate.confidence - most_recent.confidence) < 0.1:
            if self._content_differs(candidate, most_recent):
                logger.info(f"Updating memory: {candidate.memory_key}")
                return ConflictResolution.UPDATE, most_recent
        
        # 4. 置信度较低，不确定是否持久化
        if candidate.confidence < 0.6:
            logger.info(f"Uncertain memory: {candidate.memory_key} (conf={candidate.confidence})")
            return ConflictResolution.UNCERTAIN, None
        
        # 默认：跳过
        return ConflictResolution.SKIP, None
    
    def _is_duplicate(self, candidate: MemoryFact, existing: MemoryFact) -> bool:
        """判断是否重复"""
        # 1. 检查 memory_text 文本相似度
        text_similarity = self._text_similarity(candidate.memory_text, existing.memory_text)
        if text_similarity > self.similarity_threshold:
            return True
        
        # 2. 检查 value_json 是否完全相同
        if candidate.value_json and existing.value_json:
            if candidate.value_json == existing.value_json:
                return True
        
        return False
    
    def _content_differs(self, candidate: MemoryFact, existing: MemoryFact) -> bool:
        """判断内容是否不同"""
        # 1. 检查 value_json
        if candidate.value_json != existing.value_json:
            return True
        
        # 2. 检查 memory_text
        text_similarity = self._text_similarity(candidate.memory_text, existing.memory_text)
        if text_similarity < 0.7:
            return True
        
        return False
    
    @staticmethod
    def _text_similarity(text1: str, text2: str) -> float:
        """
        简单的文本相似度计算（基于字符重叠）
        
        实际生产环境可使用：
        - Levenshtein 距离
        - Jaccard 相似度
        - 语义向量余弦相似度
        """
        if not text1 or not text2:
            return 0.0
        
        # 字符集合的 Jaccard 相似度
        set1 = set(text1)
        set2 = set(text2)
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        return intersection / union if union > 0 else 0.0
