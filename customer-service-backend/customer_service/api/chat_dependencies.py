"""
依赖注入 - 符合 Slice 01 Foundation 规范
根据文档 #7、#10 定义

核心组件：
- AuthPrincipal 依赖注入
- ChatRepository 依赖注入
- TurnLock 依赖注入
"""
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from loguru import logger
from pydantic import SecretStr
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from customer_service.config.config import settings
from customer_service.context import AuthPrincipal, AgentRuntimeContext
from customer_service.infrastructure.auth import jwt_verifier
from customer_service.infrastructure.database import get_async_session
from customer_service.service.chat_repository import ChatRepository
from customer_service.service.turn_lock import TurnLock


# ==================== HTTP Bearer 安全方案 ====================
security = HTTPBearer(auto_error=True)


# ==================== Redis 连接 ====================
_redis_client: Redis | None = None


def get_redis() -> Redis:
    """
    获取 Redis 客户端（全局单例）

    注意：不记录完整 redis_url（包含密码）
    """
    global _redis_client
    if _redis_client is None:
        from redis.asyncio import from_url
        _redis_client = from_url(
            settings.redis_url,
            decode_responses=True,
            encoding="utf-8"
        )
        # 只记录连接状态，不记录完整 URL
        logger.info(f"✅ Redis 客户端已创建")
    return _redis_client


async def close_redis():
    """关闭 Redis 连接"""
    global _redis_client
    if _redis_client:
        await _redis_client.close()
        logger.info("✅ Redis 连接已关闭")


# ==================== AuthPrincipal 依赖注入 ====================
async def get_auth_principal(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> tuple[AuthPrincipal, str]:
    """
    依赖注入：从 JWT 提取 AuthPrincipal（唯一身份入口）

    根据文档 #7 定义：
    - AuthPrincipal 是唯一身份来源
    - 用户身份**只能来自 JWT.sub**，不回退到其他字段
    - frozen=True 不可变

    jwt_verifier.verify_token 已确保：
    - sub 非空
    - type = access
    - 签名、issuer、audience、exp 全部验证通过

    返回：
    - tuple[AuthPrincipal, str]: (principal, access_token)
    - access_token 用于传递给 AgentRuntimeContext，供 Commerce API 用户委托认证
    """
    token = credentials.credentials
    payload = jwt_verifier.verify_token(token)

    # 只从 sub 获取 user_id，jwt_verifier 已确保 sub 非空
    user_id = payload["sub"]

    principal = AuthPrincipal(user_id=user_id)
    logger.debug(f"✅ AuthPrincipal: user_id={principal.user_id}")
    return principal, token


# ==================== ChatRepository 依赖注入 ====================
async def get_chat_repository(
    session: AsyncSession = Depends(get_async_session)
) -> ChatRepository:
    """依赖注入：ChatRepository"""
    return ChatRepository(session)


# ==================== TurnLock 依赖注入 ====================
async def get_turn_lock() -> TurnLock:
    """
    依赖注入：TurnLock

    使用独立的短期锁超时（60秒），而不是复用checkpoint的长TTL
    防止进程中断后，同一会话被锁住过长时间
    """
    redis = get_redis()
    return TurnLock(redis, lock_timeout=60)  # 使用60秒短锁，而非checkpoint TTL


# ==================== 类型别名（简化注解） ====================
# 注意：AuthPrincipalDep 现在返回 tuple[AuthPrincipal, str]
AuthPrincipalDep = Annotated[tuple[AuthPrincipal, str], Depends(get_auth_principal)]
ChatRepositoryDep = Annotated[ChatRepository, Depends(get_chat_repository)]
TurnLockDep = Annotated[TurnLock, Depends(get_turn_lock)]
DBSessionDep = Annotated[AsyncSession, Depends(get_async_session)]


# ==================== AgentRuntimeContext 工厂 ====================
async def create_runtime_context(
    principal: AuthPrincipal,
    request_id: str,
    session_id: str,
    turn_id: str | None,
    access_token: str,
    deadline_monotonic: float
) -> AgentRuntimeContext:
    """
    创建 AgentRuntimeContext
    
    禁止持久化到：
    - LangGraph state
    - Prompt
    - Memory
    - 向量数据库
    """
    return AgentRuntimeContext(
        principal=principal,
        request_id=request_id,
        session_id=session_id,
        turn_id=turn_id,
        request_deadline_monotonic=deadline_monotonic,
        user_access_token=SecretStr(access_token)
    )
