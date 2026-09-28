"""
售后相关 Schemas
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field


class ReturnRequestCreate(BaseModel):
    """退货退款创建请求（Service 层使用）"""
    order_id: str = Field(..., description="订单ID")
    product_id: str = Field(..., description="商品ID")
    sku_id: str = Field(..., description="SKU ID")
    reason: str = Field(..., min_length=1, max_length=500, description="退货原因")


class ReturnRequestBody(BaseModel):
    """退货退款请求（API 层使用）"""
    product_id: str = Field(..., description="商品ID")
    sku_id: str = Field(..., description="SKU ID")
    reason: str = Field(..., min_length=1, max_length=500, description="退货原因")


class ExchangeRequestCreate(BaseModel):
    """换货创建请求（Service 层使用）"""
    order_id: str = Field(..., description="订单ID")
    product_id: str = Field(..., description="商品ID")
    original_sku_id: str = Field(..., description="原SKU ID")
    exchange_sku_id: str = Field(..., description="目标SKU ID")
    reason: str = Field(..., min_length=1, max_length=500, description="换货原因")


class ExchangeRequestBody(BaseModel):
    """换货请求（API 层使用）"""
    product_id: str = Field(..., description="商品ID")
    original_sku_id: str = Field(..., description="原SKU ID")
    exchange_sku_id: str = Field(..., description="目标SKU ID")
    reason: str = Field(..., min_length=1, max_length=500, description="换货原因")


class ShippingUrgeRequestCreate(BaseModel):
    """催发货创建请求（Service 层使用）"""
    order_id: str = Field(..., description="订单ID")
    reason_code: str = Field(default="NORMAL_URGE", description="NORMAL_URGE/URGENT")
    reason_detail: str | None = Field(None, max_length=500, description="详细原因")
    requested_deadline: str | None = Field(None, description="期望发货时间")


class ShippingUrgeRequestBody(BaseModel):
    """催发货请求（API 层使用）"""
    reason_code: str = Field(default="NORMAL_URGE", description="NORMAL_URGE/URGENT")
    reason_detail: str | None = Field(None, max_length=500, description="详细原因")
    requested_deadline: str | None = Field(None, description="期望发货时间")


class AfterSaleResponse(BaseModel):
    """售后响应"""
    request_id: str
    request_type: str = Field(..., description="RETURN/EXCHANGE/SHIPPING_URGE")
    order_id: str
    status: str
    refund_amount: Decimal | None = None
    original_sku_id: str | None = None
    exchange_sku_id: str | None = None

    class Config:
        from_attributes = True


class ReturnRequestResponse(BaseModel):
    """退货申请响应（供 Internal API 使用）"""
    request_id: str
    request_type: str = "RETURN"
    order_id: str
    product_id: str
    sku_id: str
    reason: str
    status: str = Field(..., description="pending/approved/rejected/completed")
    refund_amount: Decimal | None = None
    created_at: str
    updated_at: str | None = None

    class Config:
        from_attributes = True


class ExchangeRequestResponse(BaseModel):
    """换货申请响应（供 Internal API 使用）"""
    request_id: str
    request_type: str = "EXCHANGE"
    order_id: str
    product_id: str
    original_sku_id: str
    exchange_sku_id: str
    reason: str
    status: str = Field(..., description="pending/approved/in_transit/completed")
    refund_amount: Decimal = Field(default=Decimal("0.00"))
    created_at: str
    updated_at: str | None = None

    class Config:
        from_attributes = True


class ShippingUrgeRequestResponse(BaseModel):
    """催发货记录响应（供 Internal API 使用）"""
    request_id: str
    request_type: str = "SHIPPING_URGE"
    order_id: str
    reason_code: str
    reason_detail: str | None = None
    requested_deadline: str | None = None
    status: str = Field(..., description="pending/processed/shipped")
    created_at: str
    processed_at: str | None = None

    class Config:
        from_attributes = True
