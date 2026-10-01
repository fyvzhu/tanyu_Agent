"""
订单相关 Schemas
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class OrderItemRequest(BaseModel):
    """订单明细请求（用于创建订单）"""
    sku_id: str = Field(..., description="SKU ID")
    quantity: int = Field(..., gt=0, description="购买数量")


class OrderCreateRequest(BaseModel):
    """订单创建请求"""
    items: list[OrderItemRequest] = Field(..., min_length=1, description="订单商品列表")
    receiver_name: str | None = Field(None, description="收货人姓名")
    receiver_phone: str | None = Field(None, description="收货人电话")
    receiver_address: str | None = Field(None, description="收货地址")


class OrderItemInfo(BaseModel):
    """订单明细"""
    product_id: str
    sku_id: str
    quantity: int
    price: Decimal

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    """订单明细响应"""
    product_id: str
    sku_id: str
    quantity: int
    price: Decimal
    # 扩展字段：商品详细信息
    product_name: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    main_image_url: str | None = None

    class Config:
        from_attributes = True


class OrderDetail(BaseModel):
    """订单详情"""
    order_id: str
    status: str
    status_desc: str | None
    amount: Decimal
    created_at: datetime
    receiver_name: str | None
    receiver_phone: str | None
    receiver_address: str | None
    items: list[OrderItemInfo]

    class Config:
        from_attributes = True


class OrderListItem(BaseModel):
    """订单列表项"""
    order_id: str
    status: str
    amount: Decimal
    created_at: datetime

    class Config:
        from_attributes = True


class LogisticsTraceItem(BaseModel):
    """物流轨迹项"""
    trace_time: datetime
    trace_desc: str

    class Config:
        from_attributes = True


class LogisticsTraceInfo(BaseModel):
    """物流轨迹信息（用于响应）"""
    trace_time: str | None
    trace_desc: str


class LogisticsInfo(BaseModel):
    """物流信息"""
    logistics_company: str
    tracking_number: str
    status: str
    status_desc: str | None
    updated_at: datetime
    traces: list[LogisticsTraceItem]

    class Config:
        from_attributes = True


class LogisticsResponse(BaseModel):
    """物流响应（单条记录）"""
    logistics_company: str
    tracking_number: str
    status: str
    status_desc: str | None
    updated_at: str | None
    traces: list[LogisticsTraceInfo]


class OrderResponse(BaseModel):
    """订单响应（供 Internal API 使用）"""
    order_id: str
    user_id: str
    status: str
    status_desc: str | None
    amount: Decimal
    created_at: str | None
    receiver_name: str | None
    receiver_phone: str | None
    receiver_address: str | None
    items: list[OrderItemResponse]

    class Config:
        from_attributes = True
