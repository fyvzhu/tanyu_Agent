"""
直接测试 LangGraph 执行，绕过 HTTP 层
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'customer-service-backend'))

from customer_service.graph.builder import build_agent_graph
from customer_service.graph.turn_initializer import TurnInitializer
from customer_service.schemas.foundation import SessionUserContext
from customer_service.context import AgentRuntimeContext
from customer_service.api.auth.models import AuthPrincipal
from pydantic import SecretStr


async def test_langgraph_execution():
    """直接测试 LangGraph 执行"""
    print("测试 LangGraph 完整执行...\n")
    
    # 1. 构建 Graph（不带 checkpointer，避免 Redis 依赖）
    print("[1] 构建 Graph...")
    graph = build_agent_graph(checkpointer=None)
    print("  ✅ Graph 构建成功\n")
    
    # 2. 创建测试上下文
    print("[2] 创建测试上下文...")
    principal = AuthPrincipal(
        user_id="test_user_123",
        username="test_user",
        member_level="regular"
    )
    
    runtime = AgentRuntimeContext(
        principal=principal,
        request_id="test_request_001",
        session_id="test_session_001",
        turn_id="test_turn_001",
        request_deadline_monotonic=99999999.0,
        user_access_token=SecretStr("test_token")
    )
    print(f"  ✅ Runtime context 创建成功\n")
    
    # 3. 初始化 state
    print("[3] 初始化 state...")
    initial_state = TurnInitializer.initialize_turn(
        state={
            "conversation_focus": None,
            "active_task": None,
            "paused_tasks": [],
            "pending_intent_selection": None,
            "session_user_context": SessionUserContext(member_level="regular"),
        },
        current_message="你好",
        turn_id="test_turn_001",
    )
    print(f"  ✅ State 初始化成功\n")
    
    # 4. 配置
    config = {
        "configurable": {
            "thread_id": "test_user_123:test_session_001",
            "runtime": runtime,
        }
    }
    
    # 5. 执行 Graph
    print("[4] 执行 LangGraph...\n")
    try:
        final_state = await graph.ainvoke(initial_state, config=config)
        print("\n✅ LangGraph 执行成功！\n")
        
        # 输出结果
        print("[5] 结果:")
        print(f"  response_draft: {final_state.get('response_draft', 'N/A')[:100]}")
        
        intent_result = final_state.get('intent_result')
        if intent_result:
            intent_name = intent_result.intent.value if intent_result.intent else 'unknown'
            print(f"  intent: {intent_name}")
            print(f"  confidence: {intent_result.confidence}")
        
        active_task = final_state.get('active_task')
        if active_task:
            print(f"  task_status: {active_task.status}")
        
        print("\n✅ 测试通过！")
        return True
        
    except Exception as e:
        print(f"\n❌ LangGraph 执行失败: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    result = asyncio.run(test_langgraph_execution())
    sys.exit(0 if result else 1)
