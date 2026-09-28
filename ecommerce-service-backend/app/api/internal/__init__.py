"""
Internal API 路由整合
供 Agent 服务调用，需要 Service Token 认证
"""
from fastapi import APIRouter

from .products import router as products_router
from .skus import router as skus_router
from .promotions import router as promotions_router

# 创建 Internal API 根路由
internal_router = APIRouter(prefix="/internal/v1")

# 注册所有子路由
internal_router.include_router(products_router)
internal_router.include_router(skus_router)
internal_router.include_router(promotions_router)

__all__ = ["internal_router"]
