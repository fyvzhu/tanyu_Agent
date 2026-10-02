import httpx
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from test_utils import login_test_user, AGENT_URL

async def test():
    # 登录
    token = await login_test_user("user_a")
    print(f"✅ 登录成功，token: {token[:20]}...")

    # 创建会话
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f'{AGENT_URL}/api/v1/chat/sessions',
            json={'channel': 'web'},
            headers={'Authorization': f'Bearer {token}'}
        )
        session_id = resp.json()['data']['session_id']
        print(f"✅ 会话创建: {session_id}")

        # 发送消息
        resp = await client.post(
            f'{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages',
            json={'message': '查询商品15970'},
            headers={'Authorization': f'Bearer {token}'}
        )
        result = resp.json()
        print(f"✅ 收到回复: {result['data']['text'][:100]}")
        print(f"✅ 对象数量: {len(result['data']['objects'])}")
        if result['data']['objects']:
            print(f"✅ 第一个对象: {result['data']['objects'][0]}")

if __name__ == "__main__":
    asyncio.run(test())
