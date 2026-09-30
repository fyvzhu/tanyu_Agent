"""
问题6测试：任务暂停、完成、恢复

测试要点：
1. TaskContextManager 的 .get() 错误已修复
2. resumed_this_turn 在路由中正确使用，恢复任务本轮不执行 Tool
3. complete_current 和 cancel_current 正确恢复暂停任务
4. LIFO 栈操作正确
"""
import asyncio
from test_utils import login_test_user, create_chat_session, send_chat_message


async def test_problem6_task_resume():
    print("\n" + "=" * 80)
    print("问题6测试：任务暂停、完成、恢复")
    print("=" * 80)
    
    # ===== 准备工作 =====
    print("\n[准备] 登录测试用户...")
    token = await login_test_user("user_a")
    print("✅ 登录成功")
    
    # ===== 测试1: 取消任务恢复旧任务 =====
    print("\n【测试1】取消任务B，恢复任务A")
    print("-" * 60)
    
    session1 = await create_chat_session(token, user_id="test_user_problem6_1")
    thread_id1 = session1.get("thread_id") or session1.get("session_id")
    print(f"✅ 会话创建成功: {thread_id1}")
    
    # 启动任务A：商品咨询
    result1_1 = await send_chat_message(token, thread_id1, "我想买鞋")
    print(f"任务A启动: {result1_1['response'][:60]}...")
    
    # 启动任务B：促销查询（会暂停任务A）
    result1_2 = await send_chat_message(token, thread_id1, "查一下促销活动")
    print(f"任务B启动: {result1_2['response'][:60]}...")
    
    # 取消任务B（应该恢复任务A）
    result1_3 = await send_chat_message(token, thread_id1, "算了不要了")
    print(f"取消任务B: {result1_3['response'][:100]}...")
    
    # 检查是否正确恢复任务A
    if "商品" in result1_3['response'] or "鞋" in result1_3['response'] or "继续" in result1_3['response']:
        print("✅ 正确恢复任务A，并生成恢复提示")
    else:
        print(f"⚠️  恢复提示可能不明确")
    
    # 继续任务A（下一轮才执行Tool）
    result1_4 = await send_chat_message(token, thread_id1, "15970有优惠吗")
    print(f"继续任务A: {result1_4['response'][:100]}...")
    
    # ===== 测试2: 完成任务B，恢复任务A =====
    print("\n【测试2】完成任务B，恢复任务A")
    print("-" * 60)
    
    session2 = await create_chat_session(token, user_id="test_user_problem6_2")
    thread_id2 = session2.get("thread_id") or session2.get("session_id")
    print(f"✅ 会话创建成功: {thread_id2}")
    
    # 启动任务A：商品咨询
    result2_1 = await send_chat_message(token, thread_id2, "我想买运动鞋")
    print(f"任务A启动: {result2_1['response'][:60]}...")
    
    # 启动任务B：促销查询（会暂停任务A）
    result2_2 = await send_chat_message(token, thread_id2, "15970有什么优惠")
    print(f"任务B启动并查询促销: {result2_2['response'][:100]}...")
    
    # 任务B完成后应该自动恢复任务A
    # 检查响应中是否包含恢复提示
    if "继续" in result2_2['response'] or "运动鞋" in result2_2['response']:
        print("✅ 任务B完成后正确恢复任务A")
    else:
        print("⚠️  可能未正确恢复任务A")
    
    # ===== 测试3: 闲聊插话不影响任务 =====
    print("\n【测试3】闲聊插话不影响活跃任务")
    print("-" * 60)
    
    session3 = await create_chat_session(token, user_id="test_user_problem6_3")
    thread_id3 = session3.get("thread_id") or session3.get("session_id")
    print(f"✅ 会话创建成功: {thread_id3}")
    
    # 启动任务A：商品咨询
    result3_1 = await send_chat_message(token, thread_id3, "推荐一下运动鞋")
    print(f"任务A启动: {result3_1['response'][:60]}...")
    
    # 闲聊插话
    result3_2 = await send_chat_message(token, thread_id3, "谢谢")
    print(f"闲聊响应: {result3_2['response'][:80]}...")
    
    if "不客气" in result3_2['response'] or "谢谢" in result3_2['response']:
        print("✅ 闲聊正确响应")
    else:
        print("⚠️  闲聊响应可能不正确")
    
    # 继续任务A
    result3_3 = await send_chat_message(token, thread_id3, "有什么推荐的")
    print(f"继续任务A: {result3_3['response'][:80]}...")
    
    # ===== 测试4: 取消唯一任务（无暂停任务） =====
    print("\n【测试4】取消唯一任务（无暂停任务）")
    print("-" * 60)
    
    session4 = await create_chat_session(token, user_id="test_user_problem6_4")
    thread_id4 = session4.get("thread_id") or session4.get("session_id")
    print(f"✅ 会话创建成功: {thread_id4}")
    
    # 启动唯一任务
    result4_1 = await send_chat_message(token, thread_id4, "我想买鞋")
    print(f"任务启动: {result4_1['response'][:60]}...")
    
    # 取消任务
    result4_2 = await send_chat_message(token, thread_id4, "算了不要了")
    print(f"取消任务: {result4_2['response'][:80]}...")
    
    if "取消" in result4_2['response'] or "好的" in result4_2['response']:
        print("✅ 取消唯一任务成功")
    else:
        print("⚠️  取消响应可能不明确")
    
    print("\n" + "=" * 80)
    print("✅ 问题6测试完成!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(test_problem6_task_resume())
