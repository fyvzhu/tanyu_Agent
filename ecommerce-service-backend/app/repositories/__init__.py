"""
Repositories 模块
"""
from app.repositories.base import BaseRepository
from app.repositories.user import (
    UserRepository,
    UserAuthRepository,
    UserMeasurementsRepository,
    UserProfileRepository,
    UserPreferencesRepository,
)
from app.repositories.product import (
    ProductRepository,
    ProductSKURepository,
    PromotionRepository,
)
from app.repositories.order import (
    OrderRepository,
    OrderItemRepository,
    LogisticsRepository,
)
from app.repositories.after_sale import (
    ReturnRequestRepository,
    ExchangeRequestRepository,
    ShippingUrgeRepository,
)
from app.repositories.refresh_token_session_repo import RefreshTokenSessionRepository

__all__ = [
    "BaseRepository",
    # User
    "UserRepository",
    "UserAuthRepository",
    "UserMeasurementsRepository",
    "UserProfileRepository",
    "UserPreferencesRepository",
    # Product
    "ProductRepository",
    "ProductSKURepository",
    "PromotionRepository",
    # Order
    "OrderRepository",
    "OrderItemRepository",
    "LogisticsRepository",
    # After Sale
    "ReturnRequestRepository",
    "ExchangeRequestRepository",
    "ShippingUrgeRepository",
    # Auth
    "RefreshTokenSessionRepository",
]
