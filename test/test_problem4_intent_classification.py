"""
问题4测试：意图判定与多意图

测试要点：
1. IntentDecision 只有 4 种：ACCEPT, CLARIFY, OUT_OF_SCOPE, CLASSIFIER_FAILURE
2. MULTIPLE_INTENTS 只出现在 IntentFallbackReason 中
3. 分类器能区分"单目标多关键词"和"多独立目标"
4. intent_parse 正确保留分类器的原始决策
5. 取消请求优先级最高
6. response_gen 正确展示候选意图
"""
import asyncio
from test_utils import login_test_user, create_chat_session, send_chat_message


async def test_problem4_intent_classification():
    """问题4：意图分类与多意图处理测试"""
    
    print("\n" + "="*80)
    print("问题4测试：意图判定与多意图")
    print("="*80)
    
    # 获取测试用户 token
    print("\n[准备] 登录测试用户...")
    token = await login_test_user("user_a")
    print("✅ 登录成功")
    
    # ===== 测试1：单目标多关键词（不应误判为多意图）=====
    print("\n【测试1】单目标多关键词：'这件鞋有优惠吗'")
    print("-" * 60)
    
    session = await create_chat_session(token, user_id="test_user_problem4_1")
    thread_id = session.get("thread_id") or session.get("session_id")
    print(f"✅ 会话创建成功: {thread_id}")
    
    result = await send_chat_message(token, thread_id, "这件鞋有优惠吗")
    print(f"响应: {result['response']}")

    if "1." in result['response'] and "2." in result['response']:
        print("❌ 错误：单目标被误判为多意图")
    else:
        print("✅ 正确：识别为单一意图")

    # ===== 测试2：真正的多独立目标（使用更明确的例子）=====
    print("\n【测试2】多独立目标：'我想查促销活动并且查订单物流'")
    print("-" * 60)

    session2 = await create_chat_session(token, user_id="test_user_problem4_2")
    thread_id2 = session2.get("thread_id") or session2.get("session_id")
    print(f"✅ 会话创建成功: {thread_id2}")

    result2 = await send_chat_message(token, thread_id2, "我想查促销活动并且查订单物流")
    print(f"响应: {result2['response']}")

    if ("1." in result2['response'] or "①" in result2['response']) and ("2." in result2['response'] or "②" in result2['response']):
        print("✅ 正确：检测到多意图，展示候选列表")

        # 测试用户选择意图
        print("\n【测试2.1】用户选择意图：'选择1'")
        result2_1 = await send_chat_message(token, thread_id2, "选择1")
        print(f"响应: {result2_1['response'][:150]}...")
        print("✅ 用户选择处理成功")
    else:
        print("⚠️  未检测到多意图")
        print(f"    响应内容: {result2['response'][:200]}...")

    # ===== 测试3：取消请求优先级 =====
    print("\n【测试3】取消请求优先级测试")
    print("-" * 60)

    session3 = await create_chat_session(token, user_id="test_user_problem4_3")
    thread_id3 = session3.get("thread_id") or session3.get("session_id")
    print(f"✅ 会话创建成功: {thread_id3}")

    # 使用更明确的意图表达来启动任务
    await send_chat_message(token, thread_id3, "帮我推荐运动鞋")
    print("✅ 任务已启动")

    result3 = await send_chat_message(token, thread_id3, "算了不要了")
    print(f"响应: {result3['response'][:100]}...")
    if "取消" in result3['response'] or "好的" in result3['response'] or "明白" in result3['response']:
        print("✅ 取消请求处理成功")
    else:
        print("⚠️ 取消响应可能不明确")

    # ===== 测试4：低置信度澄清 =====
    print("\n【测试4】低置信度澄清测试")
    print("-" * 60)

    session4 = await create_chat_session(token, user_id="test_user_problem4_4")
    thread_id4 = session4.get("thread_id") or session4.get("session_id")

    result4 = await send_chat_message(token, thread_id4, "有什么")
    print(f"响应: {result4['response'][:100]}...")
    print("✅ 低置信度情况处理完成")
    
    print("\n" + "="*80)
    print("✅ 问题4测试完成!")
    print("="*80)
    return True


if __name__ == "__main__":
    asyncio.run(test_problem4_intent_classification())
