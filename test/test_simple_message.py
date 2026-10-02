"""
简单的消息发送测试，用于调试 LangGraph 节点问题
"""
import asyncio
import sys
import os

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'customer-service-backend'))

from customer_service.graph.state import AgentState
from customer_service.graph.nodes.intent_parse import intent_parse_node
from customer_service.graph.nodes.slot_check import slot_check_node
from customer_service.graph.nodes.tool_dispatch import tool_dispatch_node
from customer_service.graph.nodes.response_gen import response_gen_node
from customer_service.graph.nodes.hallucination_guard import hallucination_guard_node
from langgraph.types import RunnableConfig


async def test_node_signatures():
    """测试所有节点的签名是否正确"""
    print("测试节点函数签名...\n")
    
    # 创建测试 state
    test_state = AgentState(
        turn_id="test_turn_1",
        current_message="你好",
        conversation_focus=None,
        active_task=None,
        paused_tasks=[],
        pending_intent_selection=None,
    )
    
    # 创建测试 config
    test_config = RunnableConfig(
        configurable={
            "thread_id": "test_thread",
        }
    )
    
    # 测试每个节点
    nodes = [
        ("intent_parse", intent_parse_node),
        ("slot_check", slot_check_node),
        ("tool_dispatch", tool_dispatch_node),
        ("response_gen", response_gen_node),
        ("hallucination_guard", hallucination_guard_node),
    ]
    
    for node_name, node_func in nodes:
        try:
            print(f"测试节点: {node_name}")
            result = await node_func(test_state, test_config)
            print(f"  ✅ {node_name} 签名正确，返回类型: {type(result).__name__}\n")
        except TypeError as e:
            print(f"  ❌ {node_name} 签名错误: {e}\n")
            return False
        except Exception as e:
            # 其他错误（如缺少依赖）可以接受，我们只关心签名
            print(f"  ⚠️  {node_name} 运行时错误（签名正确）: {e}\n")
    
    print("✅ 所有节点签名测试通过！")
    return True


if __name__ == "__main__":
    result = asyncio.run(test_node_signatures())
    sys.exit(0 if result else 1)
