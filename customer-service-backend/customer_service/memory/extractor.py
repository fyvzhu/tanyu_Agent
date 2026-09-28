"""
Memory Candidate Extractor - 从对话中提取可持久化的记忆事实
"""
from __future__ import annotations

import logging
import re
from uuid import uuid4
from datetime import datetime, timezone

from customer_service.memory.schemas import MemoryFact, MemoryType, MemorySource, MemoryStatus

logger = logging.getLogger(__name__)


class MemoryCandidateExtractor:
    """
    从用户消息和工具结果中提取可持久化的记忆候选
    
    遵循文档 4.19 节要求：
    1. 提取 durable facts（可复用的偏好/习惯）
    2. 过滤一次性信息
    3. 标记置信度和重要性
    """
    
    # 可持久化的偏好模式
    PREFERENCE_PATTERNS = [
        (r"(我|俺|本人).*喜欢.*?(宽松|修身|紧身|合身|舒适|透气)", "fit_preference"),
        (r"(我|俺|本人).*偏好.*?(黑色|白色|灰色|蓝色|红色|黄色|绿色|紫色|粉色|藏青色)", "color_preference"),
        (r"(我|俺|本人).*预算.{0,5}?(\d+)", "budget_preference"),
        (r"(我|俺|本人).*(通勤|运动|休闲|聚会|正式|居家)", "usage_preference"),
        (r"(我|俺|本人).*一般.*?穿.*?(S|M|L|XL|XXL|小码|中码|大码)", "size_habit"),
    ]
    
    # 一次性内容（不应持久化）
    EPHEMERAL_KEYWORDS = [
        "订单号", "物流", "快递", "追踪", "单号", "退货", "换货", "售后",
        "密码", "验证码", "token", "账号", "手机号", "邮箱", "地址",
        "今天", "明天", "这次", "这个订单", "当前",
    ]
    
    def extract_from_conversation(
        self,
        user_id: str,
        session_id: str,
        turn_id: str,
        user_message: str,
        tool_result: dict | None = None,
    ) -> list[MemoryFact]:
        """
        从对话中提取记忆候选
        
        Returns:
            候选记忆事实列表
        """
        candidates = []
        
        # 1. 从用户消息中提取偏好
        candidates.extend(self._extract_preferences(user_id, session_id, turn_id, user_message))
        
        # 2. 从工具结果中提取确认的事实
        if tool_result and tool_result.get("ok"):
            candidates.extend(self._extract_from_tool_result(user_id, session_id, turn_id, tool_result))
        
        return candidates
    
    def _extract_preferences(
        self, user_id: str, session_id: str, turn_id: str, message: str
    ) -> list[MemoryFact]:
        """从用户消息中提取偏好"""
        candidates = []
        
        # 检查是否包含一次性关键词
        if any(kw in message for kw in self.EPHEMERAL_KEYWORDS):
            return candidates
        
        # 匹配偏好模式
        for pattern, memory_key in self.PREFERENCE_PATTERNS:
            match = re.search(pattern, message)
            if match:
                memory_text = match.group(0)
                value = match.group(2) if len(match.groups()) >= 2 else None
                
                fact = MemoryFact(
                    memory_id=f"MEM-{user_id}-{uuid4().hex[:8]}",
                    user_id=user_id,
                    memory_type=MemoryType.PREFERENCE,
                    memory_key=memory_key,
                    memory_text=memory_text,
                    value_json={"value": value} if value else None,
                    confidence=0.75,  # 从用户明确表达提取，置信度较高
                    importance=0.70,
                    source=MemorySource.CONVERSATION,
                    source_session_id=session_id,
                    source_turn_id=turn_id,
                    status=MemoryStatus.ACTIVE,
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                )
                candidates.append(fact)
                logger.info(f"Extracted preference: {memory_key} = {value}")
        
        return candidates
    
    def _extract_from_tool_result(
        self, user_id: str, session_id: str, turn_id: str, tool_result: dict
    ) -> list[MemoryFact]:
        """从工具结果中提取确认的事实"""
        candidates = []
        data = tool_result.get("data", {})
        
        # 从尺码推荐工具提取尺码习惯
        if "recommended_size" in data and data.get("confidence", 0) > 0.7:
            fact = MemoryFact(
                memory_id=f"MEM-{user_id}-{uuid4().hex[:8]}",
                user_id=user_id,
                memory_type=MemoryType.FACT,
                memory_key="preferred_size",
                memory_text=f"用户适合穿 {data['recommended_size']} 码",
                value_json={"size": data["recommended_size"]},
                confidence=float(data.get("confidence", 0.8)),
                importance=0.85,
                source=MemorySource.TOOL_CONFIRMED,
                source_session_id=session_id,
                source_turn_id=turn_id,
                status=MemoryStatus.ACTIVE,
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            candidates.append(fact)
        
        return candidates
