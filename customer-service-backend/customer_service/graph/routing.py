"""
LangGraph Routing Logic - 条件边路由决策
"""
from __future__ import annotations

from typing import Literal

from loguru import logger

from customer_service.graph.state import AgentState, TaskStatus, IntentDecision
from customer_service.tasking.models import BusinessIntent


def route_after_intent(state: AgentState) -> Literal["respond", "check_slots"]:
    """
    intent_parse 之后的路由决策（问题修复2：问题3）

    根据 turn_action 决定路由：
    - cancel/chitchat/clarify/select_intent/resume_notice → respond（直接生成回复）
    - accept → check_slots（检查槽位）
    - 其他 → respond（兜底）
    """
    turn_id = state.get("turn_id", "unknown")
    turn_action = state.get("turn_action")

    if not turn_action:
        logger.warning(f"[{turn_id}] ⚠️ turn_action 为空，默认 respond")
        return "respond"

    # CANCEL/CHITCHAT/CLARIFY/SELECT_INTENT/RESUME_NOTICE 直接进入 response_gen
    if turn_action in {"cancel", "chitchat", "clarify", "select_intent", "resume_notice"}:
        logger.info(f"[{turn_id}] 🔀 intent_parse 路由: respond (turn_action={turn_action})")
        return "respond"

    # ACCEPT 进入 slot_check
    if turn_action == "accept":
        logger.info(f"[{turn_id}] 🔀 intent_parse 路由: check_slots (turn_action=accept)")
        return "check_slots"

    # 其他情况默认 respond
    logger.info(f"[{turn_id}] 🔀 intent_parse 路由: respond (turn_action={turn_action}, 兜底)")
    return "respond"


def route_after_slot_check(state: AgentState) -> Literal["respond", "execute"]:
    """
    slot_check 之后的路由决策（问题修复2：问题3）

    简化后的路由逻辑（严格按文档伪代码）：
    - resumed_this_turn=True → respond（恢复任务本轮不执行 Tool）
    - missing_slots 非空 → respond（需要澄清槽位）
    - intent_result.decision != ACCEPT → respond（低置信度/多意图等）
    - 其他 → execute（执行 Tool）
    """
    turn_id = state.get("turn_id", "unknown")
    active_task = state.get("active_task")
    intent_result = state.get("intent_result")
    resumed_this_turn = state.get("resumed_this_turn", False)

    # 问题修复2-3：简化路由逻辑，按文档伪代码实现

    # 1. 检查是否恢复任务本轮（resumed_this_turn=True 不执行 Tool）
    if resumed_this_turn:
        logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (resumed_this_turn=True)")
        return "respond"

    # 2. 检查 active_task 的 missing_slots
    if active_task and hasattr(active_task, "missing_slots") and active_task.missing_slots:
        logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (missing_slots={active_task.missing_slots})")
        return "respond"

    # 3. 检查 intent_result.decision 是否为 ACCEPT
    if intent_result and hasattr(intent_result, "decision"):
        if intent_result.decision != IntentDecision.ACCEPT:
            logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (decision={intent_result.decision})")
            return "respond"

    # 4. 其他情况执行 Tool
    intent = active_task.intent if active_task else None
    logger.info(f"[{turn_id}] 🔀 slot_check 路由: execute (intent={intent.value if intent else 'unknown'})")
    return "execute"


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
