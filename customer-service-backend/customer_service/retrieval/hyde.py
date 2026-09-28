"""
HyDE (Hypothetical Document Embeddings) - 生成假设性的商品描述用于检索
"""
from __future__ import annotations

import logging

from langchain_core.language_models import BaseChatModel

from customer_service.infrastructure.llm import get_llm

logger = logging.getLogger(__name__)


class HyDEGenerator:
    """HyDE - 生成假设性的商品描述用于检索"""
    
    PROMPT_TEMPLATE = """你是商品描述专家。根据用户的需求，生成一段假设性的商品描述，用于商品检索。

用户需求: {query}

生成一段 50-100 字的商品描述，包含：
1. 商品类型和用途
2. 关键特征和卖点
3. 适用场景

只输出描述文本，不要添加标题或前缀。

示例输出：
这是一款适合夏季穿着的连衣裙，采用透气舒适的棉质面料，版型修身显瘦。简约的设计风格百搭易穿，适合日常通勤和休闲场合。颜色清新淡雅，穿着凉爽舒适。"""
    
    def __init__(self, llm: BaseChatModel | None = None):
        self.llm = llm or get_llm()
    
    async def generate(self, query: str) -> str:
        """
        生成假设性文档
        
        Args:
            query: 用户查询
        
        Returns:
            假设性的商品描述
        """
        logger.info(f"🎨 HyDE generation for: '{query}'")
        
        try:
            prompt = self.PROMPT_TEMPLATE.format(query=query)
            response = await self.llm.ainvoke(prompt)
            
            hypothetical_doc = response.content.strip()
            logger.debug(f"✅ HyDE generated: {hypothetical_doc[:50]}...")
            return hypothetical_doc
        
        except Exception as e:
            logger.warning(f"⚠️ HyDE generation failed: {e}, using original query")
            return query
