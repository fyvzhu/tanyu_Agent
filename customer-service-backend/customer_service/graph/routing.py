"""
LangGraph Routing Logic - 条件边路由决策
"""
from __future__ import annotations

from typing import Literal

from loguru import logger

from customer_service.graph.state import AgentState
from customer_service.tasking.models import BusinessIntent


def route_after_slot_check(state: AgentState) -> Literal["need_clarify", "execute_tool", "direct_response"]:
    """
    slot_check 之后的路由决策

    - need_clarify: 缺少必要槽位或低置信度，需要澄清
    - execute_tool: 槽位完整，执行工具
    - direct_response: 不需要工具（闲聊/other）
    """
    turn_id = state.get("turn_id", "unknown")
    active_task = state.get("active_task")

    # 没有 active_task，直接回复
    if not active_task:
        logger.warning(f"[{turn_id}] ⚠️ 路由决策: 没有 active_task，返回 direct_response")
        return "direct_response"

    intent = active_task.intent
    needs_clarification = state.get("needs_clarification", False)

    # 如果需要澄清
    if needs_clarification:
        logger.info(f"[{turn_id}] 🔀 路由决策: need_clarify (intent={intent.value})")
        return "need_clarify"

    # 闲聊直接回复（不需要工具）
    if intent == BusinessIntent.CHITCHAT:
        logger.info(f"[{turn_id}] 🔀 路由决策: direct_response (CHITCHAT)")
        return "direct_response"

    # 其他业务意图需要执行工具/Flow
    logger.info(f"[{turn_id}] 🔀 路由决策: execute_tool (intent={intent.value})")
    return "execute_tool"


def route_after_guard(state: AgentState) -> Literal["pass", "retry", "fallback"]:
    """
    hallucination_guard 之后的路由决策
    
    - pass: 检查通过，返回给用户
    - retry: 需要重新生成（retry_count < 2）
    - fallback: 使用确定性 fallback
    """
    guard_status = state.get("guard_status", "pass")
    
    if guard_status == "retry":
        return "retry"
    elif guard_status == "fallback":
        return "fallback"
    else:
        return "pass"
