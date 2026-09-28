"""
手动功能测试 - 验证实际业务场景

测试场景：
1. 商品详情查询（商品ID 15970）
2. 促销活动查询
3. 催发货场景（用户催平台）
"""
import asyncio
import httpx
from loguru import logger

BASE_URL = "http://localhost:8001"
AGENT_URL = "http://localhost:8000"

async def get_token():
    """获取测试用户 token"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{BASE_URL}/api/v1/auth/login",
            json={"username": "li_ming88", "password": "password123"}
        )
        resp.raise_for_status()
        return resp.json()["data"]["access_token"]

async def create_session(token):
    """创建会话"""
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions",
            headers={"Authorization": f"Bearer {token}"},
            json={"channel": "web"}
        )
        resp.raise_for_status()
        return resp.json()["data"]["session_id"]

async def send_message(token, session_id, message):
    """发送消息"""
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{AGENT_URL}/api/v1/chat/sessions/{session_id}/messages",
            headers={"Authorization": f"Bearer {token}"},
            json={"message": message}
        )
        resp.raise_for_status()
        data = resp.json()["data"]
        return data

async def test_product_detail():
    """测试1：商品详情查询（Exact Query）"""
    logger.info("\n" + "="*80)
    logger.info("测试1：商品详情查询 - 商品15970的详情是什么？")
    logger.info("="*80)
    
    token = await get_token()
    session_id = await create_session(token)
    
    result = await send_message(token, session_id, "商品15970的详情是什么？")
    
    logger.info(f"🤖 Agent: {result['text']}")
    logger.info(f"📊 意图: {result['task']['intent']}")
    logger.info(f"📊 检索上下文: {result.get('retrieved_context')}")
    
    # 验证
    if "15970" in result['text'] or "Turtle" in result['text'] or "格纹衬衫" in result['text']:
        logger.success("✅ 测试1通过：返回了商品15970的信息")
        return True
    else:
        logger.error(f"❌ 测试1失败：未返回商品15970的具体信息")
        return False

async def test_promotion_query():
    """测试2：促销活动查询"""
    logger.info("\n" + "="*80)
    logger.info("测试2：促销活动查询 - 现在有什么促销活动吗？")
    logger.info("="*80)
    
    token = await get_token()
    session_id = await create_session(token)
    
    result = await send_message(token, session_id, "现在有什么促销活动吗？")
    
    logger.info(f"🤖 Agent: {result['text']}")
    logger.info(f"📊 意图: {result['task']['intent']}")
    
    # 验证：应该提到促销信息
    if any(keyword in result['text'] for keyword in ['促销', '折扣', '优惠', '立减', 'PROMO']):
        logger.success("✅ 测试2通过：返回了促销活动信息")
        return True
    else:
        logger.error(f"❌ 测试2失败：未返回促销活动信息")
        return False

async def test_urge_shipping():
    """测试3：催发货场景（用户催平台）"""
    logger.info("\n" + "="*80)
    logger.info("测试3：催发货 - 我的订单还没发货，能催一下吗？")
    logger.info("="*80)
    
    token = await get_token()
    session_id = await create_session(token)
    
    result = await send_message(token, session_id, "我的订单还没发货，能催一下吗？")
    
    logger.info(f"🤖 Agent: {result['text']}")
    logger.info(f"📊 意图: {result['task']['intent']}")
    
    # 验证：意图应该是 urge_shipping，不是 urge_order_payment
    if result['task']['intent'] == 'urge_shipping':
        logger.success("✅ 测试3通过：正确识别为 urge_shipping 意图")
        return True
    else:
        logger.error(f"❌ 测试3失败：意图识别错误，应该是 urge_shipping，实际是 {result['task']['intent']}")
        return False

async def main():
    """运行所有测试"""
    logger.info("🚀 开始手动功能测试...")
    
    results = []
    
    # 测试1: 商品详情
    try:
        results.append(await test_product_detail())
    except Exception as e:
        logger.error(f"❌ 测试1异常: {e}")
        results.append(False)
    
    # 测试2: 促销查询
    try:
        results.append(await test_promotion_query())
    except Exception as e:
        logger.error(f"❌ 测试2异常: {e}")
        results.append(False)
    
    # 测试3: 催发货
    try:
        results.append(await test_urge_shipping())
    except Exception as e:
        logger.error(f"❌ 测试3异常: {e}")
        results.append(False)
    
    # 汇总
    logger.info("\n" + "="*80)
    passed = sum(results)
    total = len(results)
    logger.info(f"📊 测试结果: {passed}/{total} 通过 ({passed/total*100:.1f}%)")
    logger.info("="*80)

if __name__ == "__main__":
    asyncio.run(main())
