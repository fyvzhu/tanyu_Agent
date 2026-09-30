"""
测试配置和 Fixtures
"""
import pytest
import asyncio
from httpx import AsyncClient


@pytest.fixture
async def async_client():
    async with AsyncClient(base_url="http://localhost:8001") as client:
        yield client


@pytest.fixture
async def auth_headers():
    """获取认证头（用于需要JWT的API）"""
    # 使用真实测试用户登录
    async with AsyncClient(base_url="http://localhost:8001") as client:
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "username": "li_ming88",
                "password": "Limi01Aa!26"
            }
        )

        if response.status_code == 200:
            data = response.json()
            token = data["data"]["access_token"]
            return {"Authorization": f"Bearer {token}"}
        else:
            # 如果登录失败，返回空headers
            print(f"登录失败: {response.status_code}, {response.text}")
            return {}
