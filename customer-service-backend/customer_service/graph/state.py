"""
LangGraph AgentState - Slice 01 Foundation
根据 01_slice_foundation 文档 #14 定义

核心职责：
- AgentState TypedDict（Persistent + Transient）
- 从 tasking.models 导入 TaskFrame, TaskStatus, BusinessIntent, ActionMode
- 从 intents.models 导入 IntentResult, IntentDecision, IntentFallbackReason
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict

from pydantic import BaseModel, Field

# 导入统一定义的类型（避免重复定义）
from customer_service.tasking.models import (
    TaskFrame,
    TaskStatus,
    BusinessIntent,
    ActionMode,
    FocusRef,
    PendingIntentSelection,
)
from customer_service.intents.models import (
    IntentResult,
    IntentDecision,
    IntentFallbackReason,
)
from customer_service.schemas.foundation import (
    PendingConfirmation,
    SessionUserContext,
)


# ==================== TaskTransition（Graph 专用）====================

class TaskTransition(BaseModel):
    """Task 转换信息（Transient）"""
    action: Literal["start", "continue", "pause", "resume", "complete", "cancel"]
    old_task_id: str | None = None
    new_task_id: str | None = None
    reason: str | None = None


# ==================== 辅助函数（问题二修复）====================

def get_conversation_products(state: AgentState) -> list[str]:
    """
    从新字段提取对话中的商品列表

    问题二修复：替代旧的 state["conversation_products"] 和 state["short_memory"]["candidate_products"]
    现在从 active_task.slots["candidates"] 提取

    用于：
    - 序数指代映射（"第一款" → candidates[0]）
    - 歧义检测（多个候选时）
    - 唯一候选判断
    """
    products = []

    # 从 active_task.slots 提取候选商品
    active_task = state.get("active_task")
    if active_task and active_task.slots:
        candidates = active_task.slots.get("candidates", [])
        for candidate in candidates:
            if isinstance(candidate, dict):
                product_id = candidate.get("product_id")
                if product_id:
                    products.append(str(product_id))
            elif isinstance(candidate, str):
                products.append(candidate)

    # 从 conversation_focus 提取（如果是 product 类型）
    focus = state.get("conversation_focus")
    if focus and focus.entity_type == "product" and focus.entity_id:
        if focus.entity_id not in products:
            products.append(focus.entity_id)

    return products


def get_focused_product_id(state: AgentState) -> str | None:
    """
    从新字段提取当前聚焦的商品ID

    问题二修复：替代旧的 state["focused_object"]["product_id"]
    现在从 conversation_focus 提取
    """
    focus = state.get("conversation_focus")
    if focus and focus.entity_type == "product":
        return focus.entity_id
    return None


# ==================== AgentState ====================

class AgentState(TypedDict, total=False):
    """
    LangGraph AgentState - 单一真值（v7 规范）

    P0 修复：严格遵守 v7 Runtime Contract
    - ✅ JWT、user_id、session_id 不进入 AgentState
    - ✅ 通过 AgentRuntimeContext 传递（config["configurable"]["runtime"]）
    - ✅ 只保留真正需要持久化和每轮计算的字段

    Persistent 字段（持久化到 Redis Checkpointer）:
    - active_task: 当前活动任务
    - paused_tasks: 暂停的任务栈（LIFO）
    - session_user_context: 用户上下文（measurement overrides）
    - conversation_focus: 全局单一指代对象（FocusRef）
    - pending_intent_selection: 多意图待选择

    Transient 字段（每 Turn 重置，不持久化但参与计算）:
    - current_message, turn_id, intent_result, entities
    - flow_result, response_draft
    - task_transition, completed_task_snapshot, resumed_task_snapshot
    - resumed_this_turn, guard_retry_count, fallback_used

    Runtime Context（通过 config 传递，不在 State 中）:
    - session_id, user_id, user_access_token
    - 从 config["configurable"]["runtime"] 获取 AgentRuntimeContext
    """

    # ===== Persistent（v7 规范 - 持久化到 Redis）=====
    active_task: TaskFrame | None
    paused_tasks: list[TaskFrame]
    session_user_context: SessionUserContext
    conversation_focus: FocusRef | None
    pending_intent_selection: PendingIntentSelection | None

    # ===== Transient（v7 规范 - 每 Turn 重置）=====
    current_message: str
    turn_id: str
    intent_result: IntentResult | None
    entities: dict[str, Any]
    flow_result: Any  # FlowResult | None - 使用Any避免循环导入
    response_draft: str | None
    task_transition: TaskTransition | None
    completed_task_snapshot: TaskFrame | None
    resumed_task_snapshot: TaskFrame | None
    resumed_this_turn: bool
    guard_retry_count: int
    fallback_used: bool
