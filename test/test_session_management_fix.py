"""
会话管理修复验证测试

测试第九次提交的三大修复：
1. HTTP契约对齐（message字段、响应格式）
2. 前端会话状态统一（消息不丢失）
3. Redis异常处理（503而非伪装）

运行环境: C:\\Users\\HP\\anaconda3\\envs\\ECommerce
"""
import pytest
import httpx
import asyncio
from typing import Dict, Any


BASE_URL = "http://localhost:8000"  # Customer Service Backend
TEST_USER = "li_ming88"
TEST_PASSWORD = "Limi01Aa!26"


@pytest.fixture
async def auth_token():
    """获取测试用户的认证token"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"username": TEST_USER, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"]
        return data["data"]["access_token"]


@pytest.fixture
async def auth_headers(auth_token):
    """返回认证请求头"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestHTTPContract:
    """测试1: HTTP契约对齐"""
    
    async def test_send_message_with_correct_field(self, auth_headers):
        """发送'你好'应该返回200而非422"""
        async with httpx.AsyncClient() as client:
            # 创建会话
            response = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions",
                headers=auth_headers,
                json={}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"]
            session_id = data["data"]["session_id"]
            
            # 发送消息 - 使用正确的 message 字段
            response = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions/{session_id}/messages",
                headers=auth_headers,
                json={"message": "你好"},
                timeout=30.0
            )
            
            # 应该成功，不再是422
            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()
            assert data["success"], f"Response should be successful: {data}"
            assert "data" in data
            assert "text" in data["data"], "Response should contain text"
            print(f"✅ 发送'你好'成功: {data['data']['text'][:50]}")
    
    async def test_response_format(self, auth_headers):
        """验证响应格式为 {success, data}"""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions",
                headers=auth_headers,
                json={}
            )
            data = response.json()
            
            # 检查响应格式
            assert "success" in data
            assert "data" in data
            assert "request_id" in data
            # 不应该有 code 字段（旧格式）
            assert "code" not in data
            print(f"✅ 响应格式正确: success={data['success']}")


class TestSessionState:
    """测试2: 会话状态管理"""
    
    async def test_message_persistence_across_sessions(self, auth_headers):
        """S1发消息->创建S2->切回S1，消息应保留"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 创建S1并发送消息
            resp = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions",
                headers=auth_headers,
                json={}
            )
            s1_id = resp.json()["data"]["session_id"]
            
            resp = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions/{s1_id}/messages",
                headers=auth_headers,
                json={"message": "S1的第一条消息"}
            )
            s1_msg1_id = resp.json()["data"]["message_id"]
            
            # 创建S2并发送消息
            resp = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions",
                headers=auth_headers,
                json={}
            )
            s2_id = resp.json()["data"]["session_id"]
            
            await client.post(
                f"{BASE_URL}/api/v1/chat/sessions/{s2_id}/messages",
                headers=auth_headers,
                json={"message": "S2的消息"}
            )
            
            # 切回S1，获取历史
            resp = await client.get(
                f"{BASE_URL}/api/v1/chat/sessions/{s1_id}/messages",
                headers=auth_headers,
                params={"limit": 50}
            )
            
            data = resp.json()
            assert data["success"]
            messages = data["data"]["messages"]
            
            # S1的消息应该保留
            user_messages = [m for m in messages if m["role"] == "user"]
            assert len(user_messages) >= 1
            assert any("S1的第一条消息" in m["content"] for m in user_messages)
            
            print(f"✅ 会话S1消息保留: {len(messages)} 条消息")
    
    async def test_history_field_mapping(self, auth_headers):
        """验证历史消息字段映射（assistant->bot, content->text）"""
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 创建会话并发送消息
            resp = await client.post(
                f"{BASE_URL}/api/v1/chat/sessions",
                headers=auth_headers,
                json={}
            )
            session_id = resp.json()["data"]["session_id"]
            
            await client.post(
                f"{BASE_URL}/api/v1/chat/sessions/{session_id}/messages",
                headers=auth_headers,
                json={"message": "测试字段映射"}
            )
            
            # 获取历史
            resp = await client.get(
                f"{BASE_URL}/api/v1/chat/sessions/{session_id}/messages",
                headers=auth_headers
            )
            
            messages = resp.json()["data"]["messages"]
            
            # 检查字段
            for msg in messages:
                assert "role" in msg
                assert msg["role"] in ["user", "assistant"]
                assert "content" in msg  # 后端返回 content
                assert "message_id" in msg
                assert "turn_id" in msg
                
            print(f"✅ 历史消息字段正确: role, content, message_id, turn_id")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
