"""
快速测试：问题 #6 - ChatObject 持久化与历史一致性

测试商品查询是否返回完整的商品卡片（不是空壳）
"""
import asyncio
import httpx

COMMERCE_URL = "http://localhost:8001"
AGENT_URL = "http://localhost:8000"

async def login_user_a():
    """登录测试用户 user_a (li_ming88)"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(
            f"{COMMERCE_URL}/api/v1/auth/login",
            json={
                "username": "li_ming88",
                "password": "Limi01Aa!26"
            }
        )
        if resp.status_code != 200:
            print(f"❌ 登录失败: {resp.status_code} - {resp.text}")
            return None

        data = resp.json()
        print(f"登录响应: {data}")

        # 尝试不同的响应格式
        if "access_token" in data:
            token = data["access_token"]
        elif "data" in data and isinstance(data["data"], dict):
            token = data["data"].get("access_token")
        else:
            print(f"❌ 无法从响应中提取 token: {data}")
            return None

        print(f"✅ 登录成功，token: {token[:20]}...")
        return token


async def test_product_query_with_objects():
    """测试商品查询是否返回完整对象"""
    print("=" * 60)
    print("测试：商品查询 - ChatObject 完整性")
    print("=" * 60)
    
    token = await login_user_a()
    if not token:
        return False
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # 1. 创建会话
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            json={"channel": "web"},
            headers={"Authorization": f"Bearer {token}"}
        )
        if resp.status_code != 200:
            print(f"❌ 创建会话失败: {resp.status_code}")
            return False
        
        session_id = resp.json()["data"]["session_id"]
        print(f"✅ 会话创建: {session_id}")
        
        # 2. 发送商品查询
        print(f"\n📤 发送消息: '查询商品15970'")
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            json={"message": "查询商品15970"},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp.status_code != 200:
            print(f"❌ 消息发送失败: {resp.status_code}")
            print(f"响应: {resp.text[:500]}")
            return False
        
        data = resp.json()["data"]
        message_id = data["message_id"]
        text = data["text"]
        objects = data.get("objects", [])
        
        print(f"\n📥 POST 响应:")
        print(f"  message_id: {message_id}")
        print(f"  text: {text[:100]}...")
        print(f"  objects 数量: {len(objects)}")
        
        # 检查对象
        if not objects:
            print(f"\n❌ 问题 #6 失败: POST 响应没有返回 objects")
            print(f"   完整响应: {data}")
            return False
        
        # 检查是否是商品卡片
        product_cards = [obj for obj in objects if obj.get("type") == "product_card"]
        if not product_cards:
            print(f"\n❌ 问题 #6 失败: 没有 product_card 类型的对象")
            print(f"   对象类型: {[obj.get('type') for obj in objects]}")
            return False
        
        card = product_cards[0]
        print(f"\n✅ 商品卡片字段:")
        for key, value in card.items():
            print(f"  {key}: {value}")
        
        # 检查必需字段
        required = ["type", "product_id", "title"]
        missing = [f for f in required if not card.get(f)]
        if missing:
            print(f"\n❌ 缺少必需字段: {missing}")
            return False
        
        # 检查是否是空壳
        if (card.get("product") is None and 
            card.get("sku") is None and 
            card.get("data") == {}):
            print(f"\n❌ 问题 #6 失败: 返回了空壳商品卡片（旧 Schema）")
            return False
        
        print(f"\n✅ 商品卡片结构完整！")
        
        # 3. 获取历史，检查一致性
        print(f"\n📜 获取历史消息...")
        resp = await client.get(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if resp.status_code != 200:
            print(f"❌ 获取历史失败: {resp.status_code}")
            return False
        
        messages = resp.json()["data"]["messages"]
        
        # 找到对应的助手消息
        assistant_msg = None
        for msg in messages:
            if msg["role"] == "assistant" and msg["message_id"] == message_id:
                assistant_msg = msg
                break
        
        if not assistant_msg:
            print(f"❌ 历史中找不到 message_id={message_id}")
            return False
        
        history_objects = assistant_msg.get("objects", [])
        print(f"\n📜 历史消息:")
        print(f"  message_id: {assistant_msg['message_id']}")
        print(f"  objects 数量: {len(history_objects)}")
        
        if not history_objects:
            print(f"\n❌ 问题 #6 失败: 历史消息的 objects 为空")
            print(f"   这表明 objects_json 没有正确保存到数据库")
            return False
        
        # 比较 POST 和历史的对象
        if len(history_objects) != len(objects):
            print(f"❌ 对象数量不一致: POST={len(objects)}, 历史={len(history_objects)}")
            return False
        
        history_card = [obj for obj in history_objects if obj.get("type") == "product_card"][0]
        
        # 关键字段比较
        for field in ["type", "product_id", "title"]:
            if card.get(field) != history_card.get(field):
                print(f"❌ 字段 '{field}' 不一致:")
                print(f"   POST: {card.get(field)}")
                print(f"   历史: {history_card.get(field)}")
                return False
        
        print(f"\n✅✅✅ 问题 #6 验证通过！")
        print(f"  ✅ POST 响应返回完整商品卡片")
        print(f"  ✅ 历史消息的 objects 正确保存")
        print(f"  ✅ POST 与历史的对象完全一致")
        return True


async def main():
    try:
        result = await test_product_query_with_objects()
        return 0 if result else 1
    except Exception as e:
        print(f"\n❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
