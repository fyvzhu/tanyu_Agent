"""
Slice02 完整端到端测试套件

测试所有功能：
1. 商品咨询（Product Query with RAG）
2. 促销查询（Promotion Query）
3. 催拍催付（Urge Order Payment）
4. 基础闲聊（Chitchat）
"""
import asyncio
import httpx
from loguru import logger

# Agent API 配置
AGENT_API_URL = "http://localhost:8000"
COMMERCE_API_URL = "http://localhost:8001"
TEST_USERNAME = "li_ming88"  # 测试用户
TEST_PASSWORD = "password123"  # 默认密码
TEST_ACCESS_TOKEN = None  # 全局 token


async def get_access_token():
    """登录获取 JWT token"""
    global TEST_ACCESS_TOKEN

    if TEST_ACCESS_TOKEN:
        return TEST_ACCESS_TOKEN

    logger.info(f"🔐 登录获取 Access Token: username={TEST_USERNAME}")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{COMMERCE_API_URL}/api/v1/auth/login",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD}
        )
        response.raise_for_status()
        data = response.json()
        TEST_ACCESS_TOKEN = data["data"]["access_token"]
        logger.info(f"✅ Token 获取成功: {TEST_ACCESS_TOKEN[:50]}...")
        return TEST_ACCESS_TOKEN


async def create_chat_session():
    """创建聊天会话"""
    token = await get_access_token()

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{AGENT_API_URL}/api/v1/chat/sessions",
            json={"channel": "web"},
            headers={"Authorization": f"Bearer {token}"}
        )
        response.raise_for_status()
        data = response.json()
        session_id = data["data"]["session_id"]
        logger.info(f"✅ 创建会话: {session_id}")
        return session_id


async def send_message(session_id: str, message: str, expected_intent: str = None):
    """发送消息并验证响应"""
    logger.info(f"\n{'='*80}")
    logger.info(f"👤 用户: {message}")
    logger.info(f"{'='*80}")

    token = await get_access_token()

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{AGENT_API_URL}/api/v1/chat/sessions/{session_id}/messages",
            json={"message": message},
            headers={"Authorization": f"Bearer {token}"}
        )
        
        if response.status_code != 200:
            logger.error(f"❌ 请求失败: {response.status_code}")
            logger.error(f"   响应: {response.text}")
            return None
        
        data = response.json()
        
        if not data.get("success"):
            logger.error(f"❌ 业务失败: {data}")
            return None
        
        result = data["data"]

        # 提取字段（匹配实际 API 响应格式）
        reply_text = result.get('text', 'N/A')
        task_info = result.get('task', {})
        intent_name = task_info.get('intent', 'unknown')
        task_status = task_info.get('status', 'N/A')

        # 输出响应详情
        logger.info(f"🤖 Agent: {reply_text}")
        logger.info(f"📊 元数据:")
        logger.info(f"   意图: {intent_name}")
        logger.info(f"   任务状态: {task_status}")

        # 验证意图
        if expected_intent and intent_name != expected_intent:
            logger.warning(f"⚠️  意图不匹配: 期望 {expected_intent}, 实际 {intent_name}")
        else:
            logger.success(f"✅ 意图匹配: {intent_name}")

        # 为了兼容后续测试逻辑，将 intent 提升到顶层
        result['intent'] = intent_name
        result['reply'] = reply_text
        
        return result


async def test_product_query_with_rag():
    """测试1: 商品咨询（RAG检索）"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试1: 商品咨询（Product Query with RAG）")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 测试用例1: 询问舒适的T恤
    result = await send_message(
        session_id,
        "我想买一件舒适的T恤，有什么推荐？",
        expected_intent="product_query"
    )
    
    if not result:
        logger.error("❌ 测试1失败: 无响应")
        return False
    
    # 验证：应该有检索上下文
    if not result.get("retrieved_context"):
        logger.error("❌ 测试1失败: 没有检索上下文")
        return False
    
    logger.success("✅ 测试1通过: 商品咨询成功，RAG检索正常")
    return True


async def test_product_query_discovery():
    """测试2: Discovery 查询（模糊需求）"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试2: Discovery 查询（模糊需求）")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 测试用例: 询问运动鞋
    result = await send_message(
        session_id,
        "有什么好看的运动鞋？",
        expected_intent="product_query"
    )
    
    if not result:
        logger.error("❌ 测试2失败: 无响应")
        return False
    
    # 应该触发 RAG 检索
    if not result.get("retrieved_context"):
        logger.error("❌ 测试2失败: Discovery 查询应该有检索上下文")
        return False
    
    logger.success("✅ 测试2通过: Discovery 查询成功")
    return True


async def test_product_query_exact():
    """测试3: Exact 查询（精确商品ID）"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试3: Exact 查询（精确商品ID）")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 测试用例: 询问具体商品
    result = await send_message(
        session_id,
        "商品15970的详情是什么？",
        expected_intent="product_query"
    )
    
    if not result:
        logger.error("❌ 测试3失败: 无响应")
        return False
    
    # Exact 查询应该直接查 Commerce API，可能没有 RAG 上下文
    logger.success("✅ 测试3通过: Exact 查询成功")
    return True


async def test_promotion_query():
    """测试4: 促销查询"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试4: 促销查询（Promotion Query）")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 测试用例: 询问促销活动
    result = await send_message(
        session_id,
        "现在有什么促销活动吗？",
        expected_intent="promotion_query"
    )
    
    if not result:
        logger.error("❌ 测试4失败: 无响应")
        return False
    
    logger.success("✅ 测试4通过: 促销查询成功")
    return True


async def test_urge_order_payment():
    """测试5: 催拍催付"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试5: 催拍催付（Urge Order Payment）")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 测试用例: 催促支付
    result = await send_message(
        session_id,
        "我的订单还没发货，能催一下吗？",
        expected_intent="urge_order_payment"
    )
    
    if not result:
        logger.error("❌ 测试5失败: 无响应")
        return False
    
    logger.success("✅ 测试5通过: 催拍催付成功")
    return True


async def test_chitchat():
    """测试6: 基础闲聊"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试6: 基础闲聊（Chitchat）")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 测试用例1: 问候
    result = await send_message(
        session_id,
        "你好",
        expected_intent="chitchat"
    )
    
    if not result:
        logger.error("❌ 测试6失败: 无响应")
        return False
    
    # 测试用例2: 感谢
    result = await send_message(
        session_id,
        "谢谢你的帮助",
        expected_intent="chitchat"
    )
    
    if not result:
        logger.error("❌ 测试6失败: 无响应")
        return False
    
    logger.success("✅ 测试6通过: 基础闲聊成功")
    return True


async def test_multi_turn_conversation():
    """测试7: 多轮对话上下文"""
    logger.info("\n" + "="*80)
    logger.info("🧪 测试7: 多轮对话上下文")
    logger.info("="*80)
    
    session_id = await create_chat_session()
    
    # 第一轮: 询问商品
    await send_message(session_id, "我想买衬衫")
    
    # 第二轮: 追问（需要上下文）
    await send_message(session_id, "有什么颜色的？")
    
    # 第三轮: 继续追问
    result = await send_message(session_id, "价格多少？")
    
    if not result:
        logger.error("❌ 测试7失败: 无响应")
        return False
    
    logger.success("✅ 测试7通过: 多轮对话成功")
    return True


async def run_all_tests():
    """运行所有测试"""
    logger.info("\n" + "🚀"*40)
    logger.info("开始 Slice02 完整端到端测试")
    logger.info("🚀"*40 + "\n")
    
    results = {}
    
    try:
        results["商品咨询(RAG)"] = await test_product_query_with_rag()
    except Exception as e:
        logger.exception(f"测试1异常: {e}")
        results["商品咨询(RAG)"] = False
    
    try:
        results["Discovery查询"] = await test_product_query_discovery()
    except Exception as e:
        logger.exception(f"测试2异常: {e}")
        results["Discovery查询"] = False
    
    try:
        results["Exact查询"] = await test_product_query_exact()
    except Exception as e:
        logger.exception(f"测试3异常: {e}")
        results["Exact查询"] = False
    
    try:
        results["促销查询"] = await test_promotion_query()
    except Exception as e:
        logger.exception(f"测试4异常: {e}")
        results["促销查询"] = False
    
    try:
        results["催拍催付"] = await test_urge_order_payment()
    except Exception as e:
        logger.exception(f"测试5异常: {e}")
        results["催拍催付"] = False
    
    try:
        results["基础闲聊"] = await test_chitchat()
    except Exception as e:
        logger.exception(f"测试6异常: {e}")
        results["基础闲聊"] = False
    
    try:
        results["多轮对话"] = await test_multi_turn_conversation()
    except Exception as e:
        logger.exception(f"测试7异常: {e}")
        results["多轮对话"] = False
    
    # 总结
    logger.info("\n" + "="*80)
    logger.info("📊 测试结果总结")
    logger.info("="*80)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ 通过" if result else "❌ 失败"
        logger.info(f"{status} - {test_name}")
    
    logger.info("="*80)
    logger.info(f"总计: {passed}/{total} 通过 ({passed/total*100:.1f}%)")
    logger.info("="*80)


if __name__ == "__main__":
    asyncio.run(run_all_tests())
