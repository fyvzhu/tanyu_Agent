"""
TurnInitializer - Slice 01 Foundation
根据 01_slice_foundation 文档 #14.2 定义

核心职责：
- 每个新 Turn 重置 Transient 字段
- 保留 Persistent 字段
"""
from __future__ import annotations

from loguru import logger

from customer_service.graph.state import AgentState
from customer_service.schemas.foundation import SessionUserContext


class TurnInitializer:
    """
    Turn 初始化器
    
    每次新 Turn 开始时：
    - 重置所有 Transient 字段
    - 保留 Persistent 字段（active_task, paused_tasks, etc.）
    """
    
    @staticmethod
    def initialize_turn(
        state: AgentState,
        current_message: str,
        turn_id: str,
    ) -> AgentState:
        """
        初始化新 Turn
        
        Args:
            state: 当前 AgentState（可能包含上一 Turn 的 Transient 数据）
            current_message: 当前用户消息
            turn_id: 当前 Turn ID
        
        Returns:
            重置了 Transient 字段的 AgentState
        """
        logger.debug(
            f"🔄 [TurnInit] 初始化新 Turn: turn_id={turn_id}, "
            f"message='{current_message[:50]}...'"
        )
        
        # ===== 重置 Transient 字段 =====
        state["current_message"] = current_message
        state["turn_id"] = turn_id
        state["intent_result"] = None
        state["entities"] = {}
        state["flow_result"] = None
        state["response_draft"] = None
        state["task_transition"] = None
        state["completed_task_snapshot"] = None
        state["resumed_task_snapshot"] = None
        state["resumed_this_turn"] = False
        state["guard_retry_count"] = 0
        state["fallback_used"] = False
        
        # ===== 确保 Persistent 字段存在（首次 Turn） =====
        if "session_user_context" not in state:
            state["session_user_context"] = SessionUserContext()
            logger.debug("📝 [TurnInit] 初始化 session_user_context")
        
        if "paused_tasks" not in state:
            state["paused_tasks"] = []
            logger.debug("📝 [TurnInit] 初始化 paused_tasks")
        
        if "active_task" not in state:
            state["active_task"] = None
            logger.debug("📝 [TurnInit] 初始化 active_task")
        
        if "conversation_focus" not in state:
            state["conversation_focus"] = None
        
        if "pending_intent_selection" not in state:
            state["pending_intent_selection"] = None
        
        logger.info(
            f"✅ [TurnInit] Turn 初始化完成: turn_id={turn_id}, "
            f"active_task={'有' if state.get('active_task') else '无'}, "
            f"paused_tasks={len(state.get('paused_tasks', []))}"
        )
        
        return state
    
    @staticmethod
    def get_persistent_fields() -> list[str]:
        """
        返回所有 Persistent 字段名称
        
        用于 Checkpointer 选择性持久化
        """
        return [
            "active_task",
            "paused_tasks",
            "session_user_context",
            "conversation_focus",
            "pending_intent_selection",
        ]
    
    @staticmethod
    def get_transient_fields() -> list[str]:
        """
        返回所有 Transient 字段名称
        
        用于调试和验证
        """
        return [
            "current_message",
            "turn_id",
            "intent_result",
            "entities",
            "flow_result",
            "response_draft",
            "task_transition",
            "completed_task_snapshot",
            "resumed_task_snapshot",
            "resumed_this_turn",
            "guard_retry_count",
            "fallback_used",
        ]
    
    @staticmethod
    def extract_persistent_state(state: AgentState) -> dict:
        """
        提取 Persistent 字段（用于手动检查点保存）
        
        Returns:
            只包含 Persistent 字段的 dict
        """
        persistent_fields = TurnInitializer.get_persistent_fields()
        return {
            key: state.get(key)
            for key in persistent_fields
            if key in state
        }
