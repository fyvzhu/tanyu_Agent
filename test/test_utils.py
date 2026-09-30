"""
测试工具模块 - 提供所有测试共用的功能

包含：
1. 登录获取 JWT token
2. 创建测试会话
3. 发送测试消息
4. 通用配置
"""
import httpx
from typing import Optional


# ==================== 测试配置 ====================
COMMERCE_URL = "http://127.0.0.1:18081"
AGENT_URL = "http://127.0.0.1:18082"
REDIS_URL = "redis://:618618@localhost:6379"

# 预定义测试用户
TEST_USERS = {
    "user_a": {"username": "li_ming88", "password": "Limi01Aa!26"},
    "user_b": {"username": "wang_xin23", "password": "Wang02Bb!26"},
}


# ==================== 登录认证 ====================
async def get_jwt_token(username: str, password: str) -> str:
    """
    通过 Commerce 服务登录获取 JWT token
    
    Args:
        username: 用户名
        password: 密码
    
    Returns:
        JWT access token
    
    Raises:
        Exception: 登录失败时抛出异常
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{COMMERCE_URL}/api/v1/auth/login",
            json={"username": username, "password": password}
        )
        if resp.status_code != 200:
            raise Exception(f"登录失败: {resp.status_code} - {resp.text}")
        
        data = resp.json()
        return data["data"]["access_token"]


async def login_test_user(user_key: str = "user_a") -> str:
    """
    使用预定义测试用户登录
    
    Args:
        user_key: 测试用户键名 (user_a, user_b)
    
    Returns:
        JWT access token
    """
    if user_key not in TEST_USERS:
        raise ValueError(f"未知的测试用户: {user_key}")
    
    user = TEST_USERS[user_key]
    return await get_jwt_token(user["username"], user["password"])


# ==================== 会话管理 ====================
async def create_chat_session(
    token: str,
    user_id: Optional[str] = None,
    channel: str = "web"
) -> dict:
    """
    创建聊天会话
    
    Args:
        token: JWT token
        user_id: 用户ID（可选，用于测试场景）
        channel: 渠道类型
    
    Returns:
        会话数据字典，包含 session_id 和 thread_id
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        payload = {"channel": channel}
        if user_id:
            payload["user_id"] = user_id
        
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp.status_code == 200:
            return resp.json()["data"]
        elif resp.status_code == 201:
            return resp.json()
        else:
            raise Exception(f"创建会话失败: {resp.status_code} - {resp.text}")


async def send_chat_message(
    token: str,
    thread_id: str,
    message: str
) -> dict:
    """
    发送聊天消息

    Args:
        token: JWT token
        thread_id: 会话 thread_id
        message: 消息内容

    Returns:
        响应数据字典，包含 'response' 字段（即 reply）
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions/{thread_id}/messages",
            json={"message": message},
            headers={"Authorization": f"Bearer {token}"}
        )

        if resp.status_code != 200:
            raise Exception(f"发送消息失败: {resp.status_code} - {resp.text}")

        data = resp.json()
        # 返回统一格式，支持多种响应字段名
        response_text = (
            data.get("data", {}).get("text") or
            data.get("data", {}).get("reply") or
            ""
        )
        return {
            "response": response_text,
            "raw_data": data
        }


# ==================== 测试辅助 ====================
async def get_commerce_product(token: str, product_id: str) -> dict:
    """获取 Commerce 服务的商品详情"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{COMMERCE_URL}/api/v1/catalog/products/{product_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp.status_code != 200:
            raise Exception(f"获取商品失败: {resp.status_code} - {resp.text}")
        
        return resp.json()["data"]


async def get_commerce_promotions(token: str, product_id: str) -> list:
    """获取 Commerce 服务的促销信息"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{COMMERCE_URL}/api/v1/promotions/by-product/{product_id}",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp.status_code != 200:
            raise Exception(f"获取促销信息失败: {resp.status_code} - {resp.text}")
        
        return resp.json()["data"]
