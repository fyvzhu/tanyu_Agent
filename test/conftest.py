"""
Pytest 配置文件
提供全局 fixtures 和测试配置
"""
import sys
from pathlib import Path

# 添加 customer-service-backend 到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent / "customer-service-backend"))

import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from jose import jwt

from customer_service.context import AuthPrincipal


# ==================== Pytest 配置 ====================

@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环（用于 async 测试）"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# ==================== JWT Mock Fixtures ====================

def create_mock_jwt_token(user_id: str) -> str:
    """创建 Mock JWT Token（用于测试）"""
    # 使用简单的 HS256 算法创建测试 Token
    payload = {
        "sub": user_id,
        "exp": datetime.utcnow() + timedelta(hours=1),
        "iat": datetime.utcnow(),
    }
    return jwt.encode(payload, "test-secret-key", algorithm="HS256")


@pytest.fixture(autouse=True)
def mock_jwt_validation():
    """
    自动 Mock JWT 验证（所有测试自动生效）
    
    将 JWT 验证替换为简单的 token -> user_id 映射
    """
    mock_tokens = {
        "Bearer mock_token_user1": "U0001",
        "Bearer mock_token_user2": "U0002",
    }
    
    async def mock_get_auth_principal(credentials):
        """Mock 的 JWT 验证函数"""
        if not credentials:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="未提供认证凭证")
        
        auth_header = f"Bearer {credentials.credentials}"
        user_id = mock_tokens.get(auth_header)
        
        if not user_id:
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="无效的 Token")
        
        return AuthPrincipal(user_id=user_id)
    
    # Patch get_auth_principal
    with patch(
        "customer_service.api.chat_dependencies.get_auth_principal",
        side_effect=mock_get_auth_principal
    ):
        yield


# ==================== Database Fixtures ====================

@pytest.fixture
async def clean_test_db():
    """
    清理测试数据库（集成测试使用）
    
    注意：仅在测试环境使用！
    """
    from customer_service.infrastructure.database import get_async_session
    from customer_service.models.chat import ChatSession, ChatMessage
    from sqlalchemy import delete
    
    async for session in get_async_session():
        try:
            # 删除测试数据
            await session.execute(delete(ChatMessage))
            await session.execute(delete(ChatSession))
            await session.commit()
        except Exception as e:
            await session.rollback()
            raise
        finally:
            await session.close()
    
    yield
    
    # 测试后再次清理
    async for session in get_async_session():
        try:
            await session.execute(delete(ChatMessage))
            await session.execute(delete(ChatSession))
            await session.commit()
        except Exception:
            await session.rollback()
        finally:
            await session.close()


# ==================== Redis Fixtures ====================

@pytest.fixture
async def clean_test_redis():
    """清理测试 Redis 数据"""
    from customer_service.api.chat_dependencies import get_redis

    redis = get_redis()

    # 删除所有测试相关的 keys
    keys = await redis.keys("turn_lock:*")
    if keys:
        await redis.delete(*keys)

    yield redis

    # 测试后清理
    keys = await redis.keys("turn_lock:*")
    if keys:
        await redis.delete(*keys)
