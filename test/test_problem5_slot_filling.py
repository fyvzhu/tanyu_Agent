"""
问题5测试：补槽与图路由

测试要点：
1. 槽位优先级：intent_result.entities > active_task.slots > conversation_focus
2. 路由条件：检查 TaskStatus.WAITING_SLOT 而不是 needs_clarification
3. 补槽提示：针对不同意图的明确问题
4. 裸数字解析：补槽时"15970"应该被识别为 product_id

测试场景：
- "15970 有优惠吗"：应该直接识别 product_id，状态 READY
- "有优惠吗"：缺少 product_id，状态 WAITING_SLOT，明确询问商品
- 下一轮"15970"：应该补入同一任务，不新建任务
"""
import asyncio
import sys
sys.path.insert(0, 'test')

from test_utils import login_test_user, create_chat_session, send_chat_message


async def test_problem5_slot_filling():
    print("\n" + "=" * 80)
    print("问题5测试：补槽与图路由")
    print("=" * 80)

    # 准备
    print("\n[准备] 登录测试用户...")
    token = await login_test_user("user_a")
    print("✅ 登录成功")

    # ===== 测试1：单轮有 product_id，应该直接 READY =====
    print("\n【测试1】单轮有 product_id：'15970 有优惠吗'")
    print("-" * 60)

    session1 = await create_chat_session(token, user_id="test_user_problem5_1")
    thread_id1 = session1.get("thread_id") or session1.get("session_id")
    print(f"✅ 会话创建成功: {thread_id1}")

    result1 = await send_chat_message(token, thread_id1, "15970 有优惠吗")
    print(f"响应: {result1['response'][:100]}...")
    
    # 验证：不应该反问商品，应该直接查询
    if "请问" in result1['response'] or "哪件商品" in result1['response']:
        print("⚠️  缺槽提示出现（不应该）")
    else:
        print("✅ 正确：直接处理，未反问商品")

    # ===== 测试2：缺少 product_id，应该 WAITING_SLOT =====
    print("\n【测试2】缺少 product_id：'有优惠吗'")
    print("-" * 60)

    session2 = await create_chat_session(token, user_id="test_user_problem5_2")
    thread_id2 = session2.get("thread_id") or session2.get("session_id")
    print(f"✅ 会话创建成功: {thread_id2}")

    result2 = await send_chat_message(token, thread_id2, "有优惠吗")
    print(f"响应: {result2['response'][:100]}...")
    
    # 验证：应该明确询问商品
    if "请问" in result2['response'] and ("商品" in result2['response'] or "哪件" in result2['response']):
        print("✅ 正确：明确询问商品")
    else:
        print(f"⚠️  未明确询问商品\n    响应: {result2['response']}")

    # ===== 测试2.1：补槽 - 提供裸数字 "15970" =====
    print("\n【测试2.1】补槽提供裸数字：'15970'")
    print("-" * 60)

    result2_1 = await send_chat_message(token, thread_id2, "15970")
    print(f"响应: {result2_1['response'][:100]}...")
    
    # 验证：应该补入同一任务，不新建任务
    if "请问" in result2_1['response'] or "不太理解" in result2_1['response']:
        print("⚠️  补槽失败，仍在询问或表示不理解")
    else:
        print("✅ 补槽成功，开始处理促销查询")

    # ===== 测试3：订单意图缺 order_id =====
    print("\n【测试3】订单意图缺槽：'我想查物流'")
    print("-" * 60)

    session3 = await create_chat_session(token, user_id="test_user_problem5_3")
    thread_id3 = session3.get("thread_id") or session3.get("session_id")
    print(f"✅ 会话创建成功: {thread_id3}")

    result3 = await send_chat_message(token, thread_id3, "我想查物流")
    print(f"响应: {result3['response'][:100]}...")
    
    # 验证：应该明确询问订单号
    if "订单号" in result3['response'] or "订单" in result3['response']:
        print("✅ 正确：明确询问订单号")
    else:
        print(f"⚠️  未明确询问订单号\n    响应: {result3['response']}")

    print("\n" + "=" * 80)
    print("✅ 问题5测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_problem5_slot_filling())
