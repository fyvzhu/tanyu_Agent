"""
LangGraph Routing Logic - 条件边路由决策
阶段1修复：使用枚举类型，添加穷尽检查
"""
from __future__ import annotations

from typing import Literal

from loguru import logger

from customer_service.graph.state import AgentState, TaskStatus, IntentDecision
from customer_service.tasking.models import BusinessIntent
from customer_service.intents.models import TurnAction, GuardStatus  # 阶段1修复：导入枚举


def route_after_intent(state: AgentState) -> Literal["respond", "check_slots"]:
    """
    intent_parse 之后的路由决策（阶段1修复：穷尽检查）

    根据 turn_action 决定路由：
    - ACCEPT → check_slots（检查槽位）
    - 其他所有动作 → respond（直接生成回复）
    - None或未知值 → 抛出错误（契约违反）
    """
    turn_id = state.get("turn_id", "unknown")
    turn_action = state.get("turn_action")

    # 阶段1修复：turn_action 缺失是严重错误，不能默默处理
    if turn_action is None:
        error_msg = f"[{turn_id}] ❌ 契约错误: turn_action 未设置，intent_parse 节点必须设置此字段"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 阶段1修复：使用枚举类型进行穷尽检查
    if turn_action == TurnAction.ACCEPT:
        logger.info(f"[{turn_id}] 🔀 intent_parse 路由: check_slots (turn_action=ACCEPT)")
        return "check_slots"

    elif turn_action in {
        TurnAction.CANCEL,
        TurnAction.CHITCHAT,
        TurnAction.CLARIFY,
        TurnAction.SELECT_INTENT,
        TurnAction.RESUME_NOTICE,
        TurnAction.UNSUPPORTED,
        TurnAction.CLASSIFIER_FAILURE,
        TurnAction.OUT_OF_SCOPE,
    }:
        logger.info(f"[{turn_id}] 🔀 intent_parse 路由: respond (turn_action={turn_action.value})")
        return "respond"

    else:
        # 阶段1修复：未知的 turn_action 抛出错误
        error_msg = f"[{turn_id}] ❌ 契约错误: 未知的 turn_action={turn_action}"
        logger.error(error_msg)
        raise ValueError(error_msg)


def route_after_slot_check(state: AgentState) -> Literal["respond", "execute"]:
    """
    slot_check 之后的路由决策

    根据文档第212行：
    - 核实 active_task 与本轮接受的意图一致
    - 槽位已验证
    - resumed_this_turn=False
    - 才放行 execute

    路由规则：
    - resumed_this_turn=True → respond（恢复任务本轮不执行 Tool）
    - missing_slots 非空 → respond（需要澄清槽位）
    - active_task.status != READY → respond（未准备好）
    - intent_result.decision != ACCEPT → respond（低置信度/多意图等）
    - active_task.intent 与 intent_result.intent 不一致 → respond（意图不匹配）
    - 其他 → execute（执行 Tool）
    """
    turn_id = state.get("turn_id", "unknown")
    active_task = state.get("active_task")
    intent_result = state.get("intent_result")
    resumed_this_turn = state.get("resumed_this_turn", False)

    # 1. 检查是否恢复任务本轮（resumed_this_turn=True 不执行 Tool）
    if resumed_this_turn:
        logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (resumed_this_turn=True)")
        return "respond"

    # 2. 检查 active_task 的 missing_slots
    if active_task and hasattr(active_task, "missing_slots") and active_task.missing_slots:
        logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (missing_slots={active_task.missing_slots})")
        return "respond"

    # 3. 检查 active_task.status 是否为 READY
    if active_task and hasattr(active_task, "status"):
        if active_task.status != TaskStatus.READY:
            logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (status={active_task.status})")
            return "respond"

    # 4. 检查 intent_result.decision 是否为 ACCEPT
    if intent_result and hasattr(intent_result, "decision"):
        if intent_result.decision != IntentDecision.ACCEPT:
            logger.info(f"[{turn_id}] 🔀 slot_check 路由: respond (decision={intent_result.decision})")
            return "respond"

    # 5. 文档第212行：核实 active_task 与本轮接受的意图一致
    if active_task and intent_result:
        if hasattr(active_task, "intent") and hasattr(intent_result, "intent"):
            if intent_result.intent and active_task.intent != intent_result.intent:
                logger.warning(
                    f"[{turn_id}] ⚠️ 意图不一致: active_task.intent={active_task.intent.value}, "
                    f"intent_result.intent={intent_result.intent.value}"
                )
                # 意图不一致，不执行Tool
                return "respond"

    # 6. 其他情况执行 Tool
    intent = active_task.intent if active_task else None
    logger.info(f"[{turn_id}] 🔀 slot_check 路由: execute (intent={intent.value if intent else 'unknown'})")
    return "execute"


def route_after_guard(state: AgentState) -> Literal["pass", "retry", "fallback"]:
    """
    hallucination_guard 之后的路由决策（阶段1修复：穷尽检查）

    - PASS: 检查通过，返回给用户
    - RETRY: 需要重新生成（retry_count < 2）
    - FALLBACK: 使用确定性 fallback
    - None或未知值 → 抛出错误（契约违反）
    """
    turn_id = state.get("turn_id", "unknown")
    guard_status = state.get("guard_status")

    # 阶段1修复：guard_status 缺失是严重错误
    if guard_status is None:
        error_msg = f"[{turn_id}] ❌ 契约错误: guard_status 未设置，hallucination_guard 节点必须设置此字段"
        logger.error(error_msg)
        raise ValueError(error_msg)

    # 阶段1修复：使用枚举类型进行穷尽检查
    if guard_status == GuardStatus.PASS:
        logger.info(f"[{turn_id}] 🔀 guard 路由: pass")
        return "pass"
    elif guard_status == GuardStatus.RETRY:
        logger.info(f"[{turn_id}] 🔀 guard 路由: retry")
        return "retry"
    elif guard_status == GuardStatus.FALLBACK:
        logger.info(f"[{turn_id}] 🔀 guard 路由: fallback")
        return "fallback"
    else:
        # 阶段1修复：未知的 guard_status 抛出错误
        error_msg = f"[{turn_id}] ❌ 契约错误: 未知的 guard_status={guard_status}"
        logger.error(error_msg)
        raise ValueError(error_msg)
