"""
查询规划器 - 决定检索策略
"""
from __future__ import annotations

import logging
from typing import Literal

from customer_service.retrieval.models import QueryContext

logger = logging.getLogger(__name__)


class QueryPlanner:
    """查询计划器 - 决定检索策略和路径"""
    
    def plan(self, context: QueryContext) -> Literal["direct", "rag", "clarify"]:
        """
        决定查询路径（按优先级）：

        决策顺序（P0-01 修复）：
        1. query_goal == "discovery" → RAG（即使有历史 focus）
        2. query_goal == "exact_detail" → DIRECT（明确商品或唯一指代）
        3. query_goal == "unclear" + reference_kind == "ambiguous" → CLARIFY
        4. 有语义查询 → RAG（默认发现）
        5. 其他 → CLARIFY（不足以执行查询）

        Args:
            context: 查询上下文

        Returns:
            查询策略类型
        """
        # 1. Discovery 优先：即使有历史 focus，当前明确的发现需求必须走 RAG
        if context.query_goal == "discovery":
            logger.info(f"🔍 Plan: RAG (discovery request, semantic: '{context.semantic_query}')")
            return "rag"

        # 2. Exact detail: 当前消息明确商品或唯一指代
        if context.query_goal == "exact_detail":
            target_id = context.explicit_product_id or context.focused_product_id
            if target_id:
                logger.info(f"🎯 Plan: DIRECT (exact detail for product: {target_id}, reference: {context.reference_kind})")
                return "direct"
            else:
                # 标记为 exact 但没有 ID，降级到澄清
                logger.warning(f"⚠️ query_goal=exact_detail but no product_id, fallback to CLARIFY")
                return "clarify"

        # 3. Unclear + ambiguous: 指代不明确
        if context.query_goal == "unclear" and context.reference_kind == "ambiguous":
            logger.info(f"❓ Plan: CLARIFY (ambiguous reference, {len(context.conversation_products)} products in conversation)")
            return "clarify"

        # 4. 有语义查询内容，默认走 RAG 发现
        if context.semantic_query and len(context.semantic_query.strip()) > 0:
            logger.info(f"🔍 Plan: RAG (semantic query: '{context.semantic_query}')")
            return "rag"

        # 5. 只有硬约束但没有语义查询，仍然走 RAG
        if context.hard_filters and not context.semantic_query.strip():
            logger.info("🔍 Plan: RAG (filters only)")
            return "rag"

        # 6. 其他情况：需要澄清用户意图
        logger.info("❓ Plan: CLARIFY (insufficient context)")
        return "clarify"
    
    def should_use_semantic_search(self, context: QueryContext) -> bool:
        """判断是否需要使用向量检索"""
        # 如果有语义查询内容且长度 >= 2，使用向量检索
        return len(context.semantic_query.strip()) >= 2
    
    def should_use_lexical_search(self, context: QueryContext) -> bool:
        """判断是否需要使用词法检索（ES）"""
        # 如果有语义查询或硬约束，使用词法检索
        return bool(context.semantic_query.strip() or context.hard_filters)
    
    def get_retrieval_limit(self, context: QueryContext) -> int:
        """获取检索数量限制"""
        # 有硬约束时多检索一些，用于后续过滤
        if context.hard_filters:
            return 30
        return 20
