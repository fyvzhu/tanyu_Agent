"""
Multi-Query 改写器 - 生成语义变体查询
"""
from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel

from customer_service.infrastructure.llm import get_llm

logger = logging.getLogger(__name__)


class MultiQueryRewriter:
    """多查询改写器 - 生成语义变体查询"""
    
    PROMPT_TEMPLATE = """你是商品检索助手。给定一个用户查询，生成 {num_variants} 个语义相似但措辞不同的查询变体，用于提高检索召回率。

用户查询: {query}

要求：
1. 保持原始查询的核心意图
2. 使用不同的表达方式（同义词、换句话说）
3. 每行一个查询变体
4. 不要添加编号或前缀

输出示例：
适合夏天穿的连衣裙
夏季清凉款女士裙装
透气舒适的夏装连衣裙"""
    
    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_llm()
    
    async def rewrite(self, original_query: str, max_variants: int = 3) -> list[str]:
        """
        生成查询变体
        
        Args:
            original_query: 原始查询
            max_variants: 最多生成的变体数量
        
        Returns:
            查询列表（包含原始查询）
        """
        logger.info(f"🔄 Multi-query rewrite: '{original_query}'")
        
        try:
            prompt = self.PROMPT_TEMPLATE.format(
                query=original_query,
                num_variants=max_variants
            )
            response = await self.llm.ainvoke(prompt)
            
            # 解析响应
            variants = [
                line.strip() 
                for line in response.content.split("\n") 
                if line.strip()
            ]
            variants = variants[:max_variants]
            
            # 始终包含原始查询
            all_queries = [original_query] + variants
            
            logger.debug(f"✅ Generated {len(variants)} variants: {variants}")
            return all_queries
        
        except Exception as e:
            logger.warning(f"⚠️ Multi-query rewrite failed: {e}, using original only")
            return [original_query]
