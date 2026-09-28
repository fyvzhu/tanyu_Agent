"""
依赖注入模块
提供认证依赖和数据库会话依赖
"""
from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core import decode_token, verify_internal_service_token, logger
from app.database import get_db
from app.models import User


user_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="UserBearerAuth",
    description="JWT access token returned by /api/v1/auth/login",
)

service_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="InternalServiceBearerAuth",
    description="Internal service token for /internal/v1 APIs",
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(user_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从 JWT Token 获取当前用户
    用于 Public API 的用户认证

    P1-16 修复：严格以 JWT.sub 为唯一身份来源
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="无效的认证格式")

    token = credentials.credentials
    payload = decode_token(token)

    if not payload:
        raise HTTPException(status_code=401, detail="Token 无效或已过期")

    # P1-16: 使用 sub 作为 canonical user_id
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token 中缺少用户信息")

    result = await db.execute(select(User).filter(User.user_id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    return user


async def verify_service_token(
    credentials: HTTPAuthorizationCredentials | None = Security(service_bearer_scheme),
) -> bool:
    """
    验证 Internal API 的 Service Token
    用于 Agent 服务间调用
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="无效的认证格式")

    token = credentials.credentials

    if not verify_internal_service_token(token):
        logger.warning(f"无效的 Service Token 尝试")
        raise HTTPException(status_code=403, detail="无效的服务令牌")

    return True


# Service 依赖注入
async def get_auth_service(db: AsyncSession = Depends(get_db)):
    """获取认证服务实例"""
    from app.services import AuthService
    return AuthService(db)


async def get_user_service(db: AsyncSession = Depends(get_db)):
    """获取用户服务实例"""
    from app.services import UserService
    return UserService(db)


async def get_catalog_service(db: AsyncSession = Depends(get_db)):
    """获取商品目录服务实例"""
    from app.services import CatalogService
    return CatalogService(db)


async def get_order_service(db: AsyncSession = Depends(get_db)):
    """获取订单服务实例"""
    from app.services import OrderService
    return OrderService(db)


async def get_after_sale_service(db: AsyncSession = Depends(get_db)):
    """获取售后服务实例"""
    from app.services import AfterSaleService
    return AfterSaleService(db)


# 类型别名，方便使用
CurrentUser = Annotated[User, Depends(get_current_user)]
ServiceTokenVerified = Annotated[bool, Depends(verify_service_token)]
DatabaseSession = Annotated[AsyncSession, Depends(get_db)]
