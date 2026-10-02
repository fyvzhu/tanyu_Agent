"""
Schemas 模块
"""
from app.schemas.common import (
    ApiResponse,
    ErrorResponse,
    ErrorDetail,
    PaginationParams,
    PaginatedResponse,
)
from app.schemas.auth import (
    UserLoginRequest,
    UserRegisterRequest,
    LoginRequest,
    TokenResponse,
    UserBasicInfo,
    RefreshTokenRequest,
)
from app.schemas.users import (
    UserProfileResponse,
    UpdateProfileRequest,
    UserProfileUpdateRequest,
    UserProfileDetailResponse,
    UserProfileDetailUpdate,
    UserPreferenceItem,
    UserPreferencesResponse,
    UserPreferencesUpdate,
    UserMeasurementsRequest,
    UserMeasurementsUpdateRequest,
    UserMeasurementsResponse,
)
from app.schemas.catalog import (
    SKUInfo,
    ProductDetail,
    ProductDetailResponse,
    ProductWithDefaultSKU,
    ProductResponse,
    ProductSearchParams,
    PromotionInfo,
)
from app.schemas.orders import (
    OrderItemRequest,
    OrderCreateRequest,
    OrderItemInfo,
    OrderItemResponse,
    OrderDetail,
    OrderListItem,
    LogisticsTraceItem,
    LogisticsTraceInfo,
    LogisticsInfo,
    LogisticsResponse,
    OrderResponse,
)
from app.schemas.after_sale import (
    ReturnRequestCreate,
    ReturnRequestBody,
    ExchangeRequestCreate,
    ExchangeRequestBody,
    ShippingUrgeRequestCreate,
    ShippingUrgeRequestBody,
    AfterSaleResponse,
    ReturnRequestResponse,
    ExchangeRequestResponse,
    ShippingUrgeRequestResponse,
)
from app.schemas.internal import (
    BatchGetProductsRequest,
    SKUFilterRequest,
    ProductKnowledgeCard,
    ActivePromotionQuery,
)

__all__ = [
    # Common
    "ApiResponse",
    "ErrorResponse",
    "ErrorDetail",
    "PaginationParams",
    "PaginatedResponse",
    # Auth
    "UserLoginRequest",
    "UserRegisterRequest",
    "LoginRequest",
    "TokenResponse",
    "UserBasicInfo",
    "RefreshTokenRequest",
    # Users
    "UserProfileResponse",
    "UpdateProfileRequest",
    "UserProfileUpdateRequest",
    "UserProfileDetailResponse",
    "UserProfileDetailUpdate",
    "UserPreferenceItem",
    "UserPreferencesResponse",
    "UserPreferencesUpdate",
    "UserMeasurementsRequest",
    "UserMeasurementsUpdateRequest",
    "UserMeasurementsResponse",
    # Catalog
    "SKUInfo",
    "ProductDetail",
    "ProductDetailResponse",
    "ProductWithDefaultSKU",
    "ProductResponse",
    "ProductSearchParams",
    "PromotionInfo",
    # Orders
    "OrderItemRequest",
    "OrderCreateRequest",
    "OrderItemInfo",
    "OrderItemResponse",
    "OrderDetail",
    "OrderListItem",
    "LogisticsTraceItem",
    "LogisticsTraceInfo",
    "LogisticsInfo",
    "LogisticsResponse",
    "OrderResponse",
    # After Sale
    "ReturnRequestCreate",
    "ReturnRequestBody",
    "ExchangeRequestCreate",
    "ExchangeRequestBody",
    "ShippingUrgeRequestCreate",
    "ShippingUrgeRequestBody",
    "AfterSaleResponse",
    "ReturnRequestResponse",
    "ExchangeRequestResponse",
    "ShippingUrgeRequestResponse",
    # Internal
    "BatchGetProductsRequest",
    "SKUFilterRequest",
    "ProductKnowledgeCard",
    "ActivePromotionQuery",
]
