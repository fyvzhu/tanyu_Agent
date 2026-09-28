"""
LangGraph Builder - 构建 5 节点状态机主图
支持 Redis Checkpointer 用于跨 Turn 状态持久化
"""
from __future__ import annotations

from typing import Optional

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.base import BaseCheckpointSaver

from customer_service.graph.state import AgentState
from customer_service.graph.routing import route_after_slot_check, route_after_guard
from customer_service.graph.nodes.intent_parse import intent_parse_node
from customer_service.graph.nodes.slot_check import slot_check_node
from customer_service.graph.nodes.tool_dispatch import tool_dispatch_node
from customer_service.graph.nodes.response_gen import response_gen_node
from customer_service.graph.nodes.hallucination_guard import hallucination_guard_node


def build_agent_graph(checkpointer: Optional[BaseCheckpointSaver] = None):
    """
    构建 LangGraph 主状态机（唯一执行图）

    固定五节点流程：
    START → intent_parse → slot_check → [need_clarify/execute_tool/direct_response]
                                           ↓
                                      tool_dispatch → response_gen → hallucination_guard → [pass/retry/fallback] → END

    Args:
        checkpointer: LangGraph Checkpointer（支持 Redis 持久化）
                     用于 Task pause/resume、跨 Turn 状态保持
    """
    # 创建状态图
    builder = StateGraph(AgentState)

    # 添加节点（直接使用节点函数，不需要工厂）
    builder.add_node("intent_parse", intent_parse_node)
    builder.add_node("slot_check", slot_check_node)
    builder.add_node("tool_dispatch", tool_dispatch_node)
    builder.add_node("response_gen", response_gen_node)
    builder.add_node("hallucination_guard", hallucination_guard_node)

    # 设置入口
    builder.set_entry_point("intent_parse")

    # intent_parse → slot_check
    builder.add_edge("intent_parse", "slot_check")

    # slot_check → 条件路由
    builder.add_conditional_edges(
        "slot_check",
        route_after_slot_check,
        {
            "need_clarify": "response_gen",      # 需要澄清 → 直接生成澄清问题
            "execute_tool": "tool_dispatch",      # 执行工具
            "direct_response": "response_gen",    # 直接回复（闲聊/other）
        },
    )

    # tool_dispatch → response_gen
    builder.add_edge("tool_dispatch", "response_gen")

    # response_gen → hallucination_guard
    builder.add_edge("response_gen", "hallucination_guard")

    # hallucination_guard → 条件路由
    builder.add_conditional_edges(
        "hallucination_guard",
        route_after_guard,
        {
            "pass": END,           # 通过检查，结束
            "retry": "response_gen",  # 重试生成
            "fallback": END,       # 使用 fallback，结束
        },
    )

    # 编译图（带 Redis Checkpointer 支持跨 Turn 状态持久化）
    graph = builder.compile(checkpointer=checkpointer)

    return graph

