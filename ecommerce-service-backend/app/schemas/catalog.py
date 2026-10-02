"""
商品相关 Schemas
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


# ==================== 枚举定义 ====================
class StockStatus(str, Enum):
    """库存状态枚举"""
    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"


class PromotionType(str, Enum):
    """促销类型枚举"""
    PERCENTAGE_DISCOUNT = "percentage_discount"  # 原 PERCENT_OFF
    FIXED_DISCOUNT = "fixed_discount"  # 原 FIXED_OFF
    THRESHOLD_DISCOUNT = "threshold_discount"  # 原 FULL_REDUCTION
    MEMBER_PRICE = "member_price"  # 原 MEMBER_PRICE


# ==================== 内部使用的 Schema（兼容旧代码） ====================
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


# ==================== 公开 API 响应模型 ====================
class SkuPublic(BaseModel):
    """公开的 SKU 信息"""
    model_config = ConfigDict(from_attributes=True)

    sku_id: str
    product_id: str
    color: str | None = None
    size_code: str | None = None
    price: Decimal
    stock_status: StockStatus


class SkuItems(BaseModel):
    """SKU 列表响应"""
    items: list[SkuPublic]


class ProductPublic(BaseModel):
    """公开的商品详情"""
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    brand: str | None = None
    product_display_name: str
    gender: str | None = None
    category: str  # 统一的分类字段（从 type/sub_category/master_category 计算）
    main_image_url: str  # 主图 URL
    material: str | None = None
    selling_points: list[str] | None = None
    size_data: dict[str, Any] | None = None


class ProductListItem(BaseModel):
    """商品列表项"""
    model_config = ConfigDict(from_attributes=True)

    product_id: str
    brand: str | None = None
    product_display_name: str
    category: str  # 统一分类
    main_image_url: str  # 主图 URL
    min_price: Decimal  # 最低价格
    max_price: Decimal  # 最高价格
    has_stock: bool  # 是否有货


class ProductItems(BaseModel):
    """商品列表响应"""
    items: list[ProductListItem]
    total: int = 0
    page: int = 1
    page_size: int = 20


class PromotionPublic(BaseModel):
    """公开的促销信息"""
    model_config = ConfigDict(from_attributes=True)

    promotion_id: str
    title: str  # 促销标题（原 promotion_name）
    promotion_type: PromotionType
    description: str | None = None
    start_at: datetime
    end_at: datetime
    applicable: bool = True  # 是否适用（已过滤）

    # 促销参数（根据类型不同而不同）
    discount_rate: Decimal | None = None  # percentage_discount 使用
    discount_amount: Decimal | None = None  # fixed_discount 和 threshold_discount 使用
    threshold_amount: Decimal | None = None  # threshold_discount 使用
    promo_price: Decimal | None = None  # member_price 使用


class PromotionItems(BaseModel):
    """促销列表响应"""
    items: list[PromotionPublic]
