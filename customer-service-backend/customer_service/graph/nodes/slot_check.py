"""
LangGraph 节点 - Slot Check
根据 01_slice_foundation 文档 #13 定义

核心职责：
- 检查 Task 所需的 slots 是否齐全
- 决定是否需要补槽（WAITING_SLOT）
- 设置 Task 状态

P0 架构修复：
- 接受 config 参数以符合 LangGraph 规范
- 当前不使用 runtime context，但保持签名一致性
"""
from __future__ import annotations

from loguru import logger
from langgraph.types import RunnableConfig

from customer_service.graph.state import AgentState, TaskStatus
from customer_service.intents.models import BusinessIntent


# 定义每个 Intent 需要的槽位
# P0-06 修复：
# - PROMOTION_QUERY 必须有唯一 product_id（可由上下文补入）
# - URGE_ORDER_PAYMENT 不要求 order_id（催拍催付是转化对话，不是订单操作）
REQUIRED_SLOTS = {
    BusinessIntent.PRODUCT_QUERY: [],  # 可选槽位：category, keyword, brand
    BusinessIntent.SIZE_RECOMMEND: ["product_id"],  # 需要知道是哪个商品
    BusinessIntent.URGE_ORDER_PAYMENT: [],  # P0-06: 不要求 order_id，基于商品上下文和用户犹豫
    BusinessIntent.PROMOTION_QUERY: ["product_id"],  # P0-06: 必须有唯一商品才能查促销
    BusinessIntent.LOGISTICS_QUERY: ["order_id"],
    BusinessIntent.RETURN: ["order_id"],
    BusinessIntent.EXCHANGE: ["order_id"],
    BusinessIntent.CHITCHAT: [],
    BusinessIntent.URGE_SHIPPING: ["order_id"],
}


def extract_slots_from_state(state: AgentState, intent: BusinessIntent) -> dict[str, any]:
    """
    从 AgentState 中提取槽位值

    问题5修复：使用正确的优先级顺序
    优先级（由高到低）：
    1. intent_result.entities（本轮明确提取的实体）
    2. active_task.slots（已填充的槽位）
    3. conversation_focus（唯一且类型匹配的会话焦点）
    4. 从用户消息中提取（关键词匹配 + 裸数字解析）

    核心原则：本轮明确实体 > 任务已有槽位 > 会话焦点
    """
    slots = {}
    active_task = state.get("active_task")
    conversation_focus = state.get("conversation_focus")
    current_message = state.get("current_message", "")
    intent_result = state.get("intent_result")

    # 第1步：从 active_task 获取已有槽位（基线）
    if active_task:
        existing_slots = active_task.slots
        if existing_slots:
            slots.update(existing_slots)

    # 第2步：从 conversation_focus 提取（只在不冲突时使用）
    if conversation_focus:
        entity_type = conversation_focus.entity_type
        entity_id = conversation_focus.entity_id

        if entity_type == "product" and entity_id:
            slots.setdefault("product_id", entity_id)  # 使用 setdefault，已有的不覆盖
        elif entity_type == "order" and entity_id:
            slots.setdefault("order_id", entity_id)

    # 第3步：从用户消息中提取（关键词 + 裸数字）
    message_lower = current_message.lower()

    # 提取商品类别（简单关键词匹配）
    if "t恤" in message_lower or "T恤" in current_message:
        slots.setdefault("category", "T恤")
    elif "裤子" in message_lower:
        slots.setdefault("category", "裤子")
    elif "鞋" in message_lower:
        slots.setdefault("category", "鞋")

    # 问题5修复：如果任务在等待 product_id，且消息是纯数字，解析为 product_id
    if active_task and active_task.missing_slots and "product_id" in active_task.missing_slots:
        # 检查是否是纯数字或包含数字
        import re
        numbers = re.findall(r'\d+', current_message.strip())
        if numbers:
            # 取第一个数字作为 product_id
            slots["product_id"] = numbers[0]
            logger.info(f"从补槽回答中提取 product_id={numbers[0]}")

    # 问题5修复：如果任务在等待 order_id，且消息是纯数字，解析为 order_id
    if active_task and active_task.missing_slots and "order_id" in active_task.missing_slots:
        import re
        numbers = re.findall(r'\d+', current_message.strip())
        if numbers:
            slots["order_id"] = numbers[0]
            logger.info(f"从补槽回答中提取 order_id={numbers[0]}")

    # 第4步（最高优先级）：从 intent_result.entities 提取本轮明确实体
    # 这一步会覆盖前面的值
    if intent_result and intent_result.entities:
        for entity_type, entity_value in intent_result.entities.items():
            if entity_value:  # 只有非空值才覆盖
                slots[entity_type] = entity_value
                logger.info(f"使用本轮明确实体覆盖: {entity_type}={entity_value}")

    return slots


async def slot_check_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    节点 2: Slot Check

    逻辑：
    1. 检查当前 Task 的 slots 是否齐全
    2. 如果缺少 slots，设置 Task 状态为 WAITING_SLOT
    3. 如果 slots 齐全，设置状态为 READY（或继续）
    """
    turn_id = state.get("turn_id", "unknown")
    active_task = state.get("active_task")

    logger.info(f"[{turn_id}] === 节点 2: Slot Check 开始 ===")

    if not active_task:
        logger.warning(f"[{turn_id}] ⚠️ 没有 active_task，跳过 Slot Check")
        return state

    # P0 修复: 处理从 Redis 恢复的 LangChain 序列化格式
    if isinstance(active_task, dict):
        from customer_service.tasking.models import TaskFrame
        # 检查是否是 LangChain 序列化格式 (包含 'lc', 'type', 'kwargs')
        if 'kwargs' in active_task and 'lc' in active_task:
            active_task = TaskFrame(**active_task['kwargs'])
        else:
            active_task = TaskFrame(**active_task)
        state["active_task"] = active_task

    intent = active_task.intent

    # 获取该 Intent 需要的槽位
    required_slots = REQUIRED_SLOTS.get(intent, [])

    # 从 State 中提取槽位
    extracted_slots = extract_slots_from_state(state, intent)

    # 更新 active_task 的 slots
    active_task.slots.update(extracted_slots)

    # 检查缺失的槽位
    missing_slots = []
    for slot_name in required_slots:
        if slot_name not in active_task.slots or not active_task.slots[slot_name]:
            missing_slots.append(slot_name)

    # 设置状态
    if missing_slots:
        active_task.status = TaskStatus.WAITING_SLOT
        active_task.missing_slots = missing_slots
        logger.warning(
            f"[{turn_id}] ⚠️ 缺少槽位: {missing_slots}, "
            f"标记为 WAITING_SLOT"
        )
    else:
        active_task.status = TaskStatus.READY
        active_task.missing_slots = []
        logger.info(
            f"[{turn_id}] ✅ 槽位完整，标记为 READY. "
            f"slots={active_task.slots}"
        )

    state["active_task"] = active_task

    logger.info(
        f"[{turn_id}] === 节点 2: Slot Check 完成 === "
        f"status={active_task.status}, missing_slots={active_task.missing_slots}"
    )

    return state
