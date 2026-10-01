"""
Public API 路由整合
供 C 端用户直接调用，需要 JWT Token 认证
"""
from fastapi import APIRouter

from .auth import router as auth_router
from .user import router as user_router, profile_router
from .catalog import router as catalog_router
from .orders import router as orders_router
from .after_sale import router as after_sale_router

# 创建 Public API 根路由
public_router = APIRouter(prefix="/api/v1")

# 注册所有子路由
public_router.include_router(auth_router)
public_router.include_router(user_router)
public_router.include_router(profile_router)  # 添加兼容路由
public_router.include_router(catalog_router)
public_router.include_router(orders_router)
public_router.include_router(after_sale_router)

__all__ = ["public_router"]
