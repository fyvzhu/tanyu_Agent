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
    商品知识卡片（供 RAG 使用）

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
    main_image_url: str | None = Field(None, description="主图URL")
    size_chart_url: str | None = Field(None, description="尺码表URL")

    class Config:
        from_attributes = True


class ActivePromotionQuery(BaseModel):
    """有效促销查询参数"""
    member_level: str | None = Field(None, description="PLUS/普通会员")
    at: str | None = Field(None, description="查询时间点（ISO 8601）")
