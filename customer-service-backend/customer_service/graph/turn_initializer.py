"""
TurnInitializer - Slice 01 Foundation
根据 01_slice_foundation 文档 #14.2 定义

核心职责：
- 每个新 Turn 重置 Transient 字段
- 保留 Persistent 字段

阶段4修复（文档第83-88行）：
- 处理 client_context（商品/订单点击）
- 验证对象ID，不信任客户端提供的事实
- 只携带验证后的 ID，不持久化原始 client_context
"""
from __future__ import annotations

from typing import Any
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
        client_context: dict[str, Any] | None = None,
    ) -> AgentState:
        """
        初始化新 Turn

        阶段4修复：添加 client_context 参数处理商品/订单点击

        Args:
            state: 当前 AgentState（可能包含上一 Turn 的 Transient 数据）
            current_message: 当前用户消息
            turn_id: 当前 Turn ID
            client_context: 客户端上下文（商品/订单点击等）

        Returns:
            重置了 Transient 字段的 AgentState
        """
        logger.debug(
            f"🔄 [TurnInit] 初始化新 Turn: turn_id={turn_id}, "
            f"message='{current_message[:50]}...', "
            f"client_context={'有' if client_context else '无'}"
        )

        # ===== 重置 Transient 字段 =====
        state["current_message"] = current_message
        state["turn_id"] = turn_id
        state["turn_action"] = None  # 文档第202行：每轮重置
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

        # 阶段4修复：处理 client_context
        # 根据文档第85行："发送体尽量只携带 type 与 ID，辅以本轮文本"
        state["client_context"] = None  # 不持久化原始 client_context
        state["verified_object_id"] = None  # 仅保存验证后的 ID

        if client_context:
            verified_id = TurnInitializer._process_client_context(client_context, turn_id)
            if verified_id:
                state["verified_object_id"] = verified_id
                logger.info(f"[{turn_id}] ✅ 客户端对象已验证: {verified_id}")

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
    def _process_client_context(
        client_context: dict[str, Any],
        turn_id: str
    ) -> dict[str, str] | None:
        """
        阶段4修复：处理和验证 client_context

        根据文档第84-85行：
        - "必须区分'点击指定对象'和'浏览器提供业务事实'"
        - "发送体尽量只携带 type 与 ID，辅以本轮文本"
        - "不要把原始客户端 dict 持久化成 conversation_focus"

        验证规则：
        1. 只接受 type 和 id 字段
        2. 不信任客户端提供的价格、库存、名称等
        3. ID 格式校验（数字字符串）
        4. 返回验证后的对象引用

        Args:
            client_context: 客户端上下文
            turn_id: 当前 Turn ID

        Returns:
            验证后的对象引用 {"type": "product"/"order", "id": "xxx"}
            如果验证失败返回 None
        """
        if not client_context:
            return None

        # 提取 type 和 id
        obj_type = client_context.get("type")
        obj_id = client_context.get("id")

        if not obj_type or not obj_id:
            logger.warning(f"[{turn_id}] ⚠️ client_context 缺少 type 或 id: {client_context}")
            return None

        # 类型校验
        if obj_type not in ["product", "order"]:
            logger.warning(f"[{turn_id}] ⚠️ 不支持的对象类型: {obj_type}")
            return None

        # ID 格式校验（应该是数字字符串）
        if not isinstance(obj_id, (str, int)):
            logger.warning(f"[{turn_id}] ⚠️ 无效的 ID 格式: {obj_id}")
            return None

        # 转换为字符串
        obj_id = str(obj_id)

        # 商品ID校验（4-6位数字）
        if obj_type == "product":
            if not obj_id.isdigit() or len(obj_id) < 4 or len(obj_id) > 6:
                logger.warning(f"[{turn_id}] ⚠️ 无效的商品ID格式: {obj_id}")
                return None

        # 订单ID校验（8位以上数字）
        elif obj_type == "order":
            if not obj_id.isdigit() or len(obj_id) < 8:
                logger.warning(f"[{turn_id}] ⚠️ 无效的订单ID格式: {obj_id}")
                return None

        # 警告：如果客户端传了其他字段（价格、库存等），不使用
        extra_fields = set(client_context.keys()) - {"type", "id"}
        if extra_fields:
            logger.warning(
                f"[{turn_id}] ⚠️ client_context 包含不信任的字段，已忽略: {extra_fields}"
            )

        logger.info(f"[{turn_id}] ✅ 客户端对象验证通过: type={obj_type}, id={obj_id}")

        return {
            "type": obj_type,
            "id": obj_id
        }
    
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
