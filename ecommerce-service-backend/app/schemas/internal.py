"""
Internal API Schemas
用于 Agent 调用的内部接口
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class BatchGetProductsRequest(BaseModel):
    """批量获取商品请求"""
    product_ids: list[str] = Field(..., min_length=1, max_length=100)


class SKUFilterRequest(BaseModel):
    """SKU 筛选请求"""
    product_ids: list[str] | None = None
    colors: list[str] | None = None
    sizes: list[str] | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    stock_status: str | None = None


class ProductKnowledgeCard(BaseModel):
    """
    商品知识卡片（供 RAG 索引使用）

    ⚠️ 重要区别：ProductKnowledgeCard vs ProductCard

    ProductKnowledgeCard（此类）：
    - 用途：离线索引和语义检索
    - 数据来源：Commerce API /internal/v1/products/{id}/knowledge-card
    - 使用位置：IndexBuilder 离线构建向量索引
    - 包含：稳定的事实信息（品牌、材质、卖点）
    - 不含：实时价格、库存状态、用户专属促销

    ProductCard（Agent 前端展示）：
    - 用途：前端展示对象
    - 数据来源：Commerce API /api/v1/catalog/products/{id}（实时查询）
    - 使用位置：ProductFlow 根据用户查询动态生成
    - 包含：实时价格、库存、可能的用户专属促销

    字段说明：
    - main_image_url: 静态图片路径（仅供索引），不保证当前可访问
    - selling_points, features: 稳定的商品描述，用于语义检索

    使用场景：
    ✅ 离线索引构建：IndexBuilder 调用 knowledge_card() 端点
    ✅ 向量切块：Chunker 处理 KnowledgeCard 生成文本块
    ✅ 语义检索：Qdrant/ES 检索时使用切块内容

    禁止场景：
    ❌ 不要直接展示给前端用户（应组装 ProductCard）
    ❌ 不要用于价格/库存判断（数据可能过期）
    ❌ 不要写入用户专属信息（索引是共享的）

    稳定索引字段，不包含动态的价格/库存/促销
    """
    product_id: str
    brand: str | None = None
    product_display_name: str
    category: str | None = None
    material: str | None = None
    selling_points: list[str] = Field(default_factory=list, description="卖点列表")
    features: list[str] = Field(default_factory=list, description="特性列表")
    size_summary: str | None = Field(None, description="尺码总结")
    main_image_url: str | None = Field(
        None,
        description="静态图片路径（仅供索引）。展示时必须使用 ProductCard 的 main_image_url"
    )
    size_chart_url: str | None = Field(None, description="尺码表URL")

    class Config:
        from_attributes = True


class ActivePromotionQuery(BaseModel):
    """有效促销查询参数"""
    member_level: str | None = Field(None, description="PLUS/普通会员")
    at: str | None = Field(None, description="查询时间点（ISO 8601）")
