"""
商品相关 Schemas
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field


class SKUInfo(BaseModel):
    """SKU 信息"""
    sku_id: str
    product_id: str | None = None
    color: str | None
    size_code: str | None
    price: Decimal
    stock_status: str

    class Config:
        from_attributes = True


class ProductDetail(BaseModel):
    """商品详情（SPU）"""
    product_id: str
    brand: str | None
    product_display_name: str
    gender: str | None
    master_category: str | None
    sub_category: str | None
    type: str | None
    material: str | None
    selling_points: list[str] | None
    size_data: dict[str, Any] | None

    class Config:
        from_attributes = True


class ProductWithDefaultSKU(BaseModel):
    """商品及默认 SKU"""
    product_id: str
    brand: str | None
    product_display_name: str
    default_sku: SKUInfo | None

    class Config:
        from_attributes = True


# 别名，用于 API 层
ProductResponse = ProductWithDefaultSKU
ProductDetailResponse = ProductDetail


class ProductSearchParams(BaseModel):
    """商品搜索参数"""
    q: str | None = Field(None, description="搜索关键词")
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    in_stock: bool = True


class PromotionInfo(BaseModel):
    """促销信息"""
    promotion_id: str
    promotion_name: str
    promotion_type: str
    discount_amount: Decimal | None
    discount_rate: Decimal | None
    promo_price: Decimal | None
    description: str | None

    class Config:
        from_attributes = True
