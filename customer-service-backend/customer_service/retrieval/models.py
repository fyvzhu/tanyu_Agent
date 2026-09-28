"""
RAG 相关的数据模型
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class QueryContext(BaseModel):
    """查询上下文 - 包含语义查询和结构化过滤条件"""

    original_query: str
    """原始用户查询"""

    semantic_query: str
    """语义查询部分（移除硬约束后）"""

    hard_filters: dict[str, Any] = Field(default_factory=dict)
    """硬约束：brand, color, size, price_range 等"""

    soft_signals: dict[str, Any] = Field(default_factory=dict)
    """软信号：用户偏好、历史交互等"""

    explicit_product_id: str | None = None
    """本条消息明确指定的商品 ID"""

    focused_product_id: str | None = None
    """历史焦点商品 ID（仅作为上下文）"""

    reference_kind: Literal["explicit", "anaphora", "none", "ambiguous"] = "none"
    """指代类型：explicit=明确ID, anaphora=指代词, none=无指代, ambiguous=歧义"""

    query_goal: Literal["exact_detail", "discovery", "compare", "unclear"] = "unclear"
    """查询目标：exact_detail=查询具体商品, discovery=发现新商品, compare=对比, unclear=不明确"""

    conversation_products: list[str] = Field(default_factory=list)
    """对话中提到的商品 ID 列表"""


class ProductChunk(BaseModel):
    """商品文本块 - 用于向量检索的基本单位"""
    
    chunk_id: str
    """{product_id}:{chunk_type}:{ordinal}"""
    
    product_id: str
    """商品 ID"""
    
    chunk_type: Literal["overview", "selling_points", "material", "size"]
    """文本块类型"""
    
    text: str
    """文本内容"""
    
    metadata: dict[str, Any] = Field(default_factory=dict)
    """额外的元数据"""


class RetrievalResult(BaseModel):
    """检索结果 - 包含商品列表和相关元信息"""
    
    product_ids: list[str]
    """检索到的商品 ID 列表（按分数排序）"""
    
    scores: dict[str, float]
    """商品 ID -> 融合后的分数"""
    
    matched_reasons: dict[str, list[str]]
    """商品 ID -> 匹配原因列表（标签、属性等）"""
    
    mode: str
    """检索模式: qdrant+es, qdrant_only, es_only, commerce_only_degraded"""
    
    evidence: list[dict[str, Any]]
    """检索证据链（用于调试和可观测性）"""
    
    degraded: bool = False
    """是否处于降级模式"""
