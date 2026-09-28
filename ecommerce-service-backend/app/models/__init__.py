"""
数据模型模块
导出所有17张表的模型
"""
from app.models.user import User, UserAuth, UserMeasurements, UserProfile, UserPreferences
from app.models.product import Product, ProductSKU, Promotion
from app.models.order import Order, OrderItem, LogisticsRecord, LogisticsTrace
from app.models.after_sale import ReturnRequest, ExchangeRequest, ShippingUrgeRequest
from app.models.auth_session import RefreshTokenSession
from app.models.idempotency import IdempotencyRecord

__all__ = [
    # 用户体系 (5张)
    "User",
    "UserAuth",
    "UserMeasurements",
    "UserProfile",
    "UserPreferences",
    # 商品体系 (3张)
    "Product",
    "ProductSKU",
    "Promotion",
    # 订单体系 (4张)
    "Order",
    "OrderItem",
    "LogisticsRecord",
    "LogisticsTrace",
    # 售后体系 (3张)
    "ReturnRequest",
    "ExchangeRequest",
    "ShippingUrgeRequest",
    # 认证体系 (2张)
    "RefreshTokenSession",
    "IdempotencyRecord",
]
