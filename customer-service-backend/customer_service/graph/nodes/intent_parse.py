"""
LangGraph 节点 - Intent Parse
根据 01_slice_foundation 文档 #20 Intent Pipeline 定义

核心职责：
- 识别用户意图（Intent Classification）
- 处理 Task Cancel、Pending Confirmation、Pending Intent Selection
- 决定是启动新任务还是继续当前任务

Pipeline 顺序：
1. TaskCancel 优先解析
2. PendingConfirmation 检查
3. PendingIntentSelection 检查（P1-21 修复）
4. Deterministic rules
5. Structured classifier
6. IntentDecision

未知 Intent 处理：
- recognized=false, intent=null
- decision=CLARIFY / OUT_OF_SCOPE / CLASSIFIER_FAILURE / MULTIPLE_INTENTS
- 不能偷偷变成 CHITCHAT

P0 架构修复：
- 接受 config 参数以符合 LangGraph 规范
- 当前不使用 runtime context，但保持签名一致性

P1-21 修复：
- 处理 MULTIPLE_INTENTS 决策，创建 pending_intent_selection
- 解析用户对多意图的选择（数字、序号、意图名称等）
"""
from __future__ import annotations

from loguru import logger
from langgraph.types import RunnableConfig

from customer_service.graph.state import (
    AgentState,
    IntentDecision,
    IntentResult,
    ActionMode,
)
from customer_service.graph.task_context_manager import TaskContextManager
from customer_service.intents.models import BusinessIntent, IntentFallbackReason
from customer_service.intents.policies import get_intent_policy
from customer_service.tasking.models import PendingIntentSelection


async def intent_parse_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    节点 1: Intent Parse

    逻辑：
    1. 检查是否有 pending_intent_selection（多意图澄清）- P1-21
    2. 检查是否是 Task Cancel 提示词
    3. 检查是否是 Pending Confirmation 的回应
    4. 使用 Intent Pipeline 识别意图
    5. 决定启动新任务或继续当前任务

    P1-21 修复：
    - 处理 MULTIPLE_INTENTS 决策
    - 解析用户对多意图的选择
    """
    turn_id = state.get("turn_id", "unknown")
    current_message = state.get("current_message", "")

    logger.info(f"[{turn_id}] === 节点 1: Intent Parse 开始 ===")
    logger.debug(f"[{turn_id}] 用户输入: '{current_message[:100]}...'")

    # ===== 问题4修复: 优先处理取消请求 =====
    # 取消优先级最高，在所有其他处理之前
    active_task = state.get("active_task")
    pending_selection = state.get("pending_intent_selection")

    if (active_task or pending_selection) and _is_cancel_request(current_message):
        logger.info(f"[{turn_id}] ❌ 检测到取消请求")

        # 清空 pending_intent_selection（如果有）
        if pending_selection:
            state["pending_intent_selection"] = None
            logger.info(f"[{turn_id}] 🧹 清空 pending_intent_selection")

        # 取消当前任务（如果有）
        if active_task:
            state = TaskContextManager.cancel_current(
                state,
                turn_id=turn_id,
            )

        # 返回取消确认
        intent_result = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.OUT_OF_SCOPE,
            confidence=1.0,
            entities={},
        )
        state["intent_result"] = intent_result
        logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（取消）===")
        return state

    # ===== 问题4修复: 处理 pending_intent_selection =====
    if pending_selection:
        logger.info(f"[{turn_id}] 🔍 检测到 pending_intent_selection，尝试解析用户选择")

        # 从Redis恢复时，pending_selection 可能是LangChain序列化的字典
        if isinstance(pending_selection, dict):
            pending_selection = PendingIntentSelection(**pending_selection.get("kwargs", {}))
            state["pending_intent_selection"] = pending_selection

        selected_intent = _parse_intent_selection(
            current_message,
            pending_selection.candidate_intents
        )

        if selected_intent:
            logger.info(f"[{turn_id}] ✅ 用户选择了意图: {selected_intent.value}")

            # 清空 pending_intent_selection
            state["pending_intent_selection"] = None

            # 构造 IntentResult（直接 ACCEPT）
            policy = get_intent_policy(selected_intent)
            action_mode = ActionMode.ACTION_REQUEST if policy.requires_action_request else ActionMode.INFORMATIONAL

            intent_result = IntentResult(
                recognized=True,
                intent=selected_intent,
                decision=IntentDecision.ACCEPT,
                confidence=1.0,
                entities={},
                action_mode=action_mode,
            )
            state["intent_result"] = intent_result

            # 启动任务
            state = TaskContextManager.start_task(
                state,
                intent=selected_intent,
                turn_id=turn_id,
            )
            logger.info(f"[{turn_id}] 🆕 根据用户选择启动任务: {selected_intent.value}")
            logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成 ===")
            return state
        else:
            # 解析失败，返回澄清提示
            logger.warning(f"[{turn_id}] ❌ 无法解析用户选择，返回 CLARIFY")
            intent_result = IntentResult(
                recognized=False,
                intent=None,
                decision=IntentDecision.CLARIFY,
                confidence=0.0,
                entities={},
                candidate_intents=pending_selection.candidate_intents,
            )
            state["intent_result"] = intent_result
            logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（澄清）===")
            return state

    # ===== 取消检测已移到最前面，这里删除重复代码 =====

    # ===== 调用真实的 Intent Classifier =====
    from customer_service.intents.classifier import IntentClassifier

    classifier = IntentClassifier()
    classification_result = classifier.classify(current_message)

    # 问题4修复: 处理分类器返回的 CLARIFY (包括 MULTIPLE_INTENTS 原因)
    if classification_result.decision == IntentDecision.CLARIFY:
        # 检查是否是多意图情况
        if (classification_result.fallback_reason == IntentFallbackReason.MULTIPLE_INTENTS
            and len(classification_result.candidate_intents) >= 2):
            logger.info(
                f"[{turn_id}] 🔀 检测到多意图: {[i.value for i in classification_result.candidate_intents]}, "
                f"margin={classification_result.margin:.2f}"
            )

            # 创建 pending_intent_selection
            state["pending_intent_selection"] = PendingIntentSelection(
                candidate_intents=classification_result.candidate_intents,
                original_turn_id=turn_id,
            )

            # 保留分类器的原始 IntentResult
            state["intent_result"] = classification_result
            logger.info(f"[{turn_id}] ⏸️ 等待用户选择意图，不启动任务")
            logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（多意图）===")
            return state
        else:
            # 其他 CLARIFY 原因：LOW_CONFIDENCE 等
            logger.info(
                f"[{turn_id}] ❓ 需要澄清: reason={classification_result.fallback_reason}, "
                f"confidence={classification_result.confidence:.2f}"
            )
            # 保留分类器的原始决策
            state["intent_result"] = classification_result
            logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（澄清）===")
            return state

    # 问题4修复: 保留 OUT_OF_SCOPE 和 CLASSIFIER_FAILURE 的原始决策
    if classification_result.decision in (IntentDecision.OUT_OF_SCOPE, IntentDecision.CLASSIFIER_FAILURE):
        logger.warning(
            f"[{turn_id}] ⚠️ 分类器决策: {classification_result.decision.value}, "
            f"reason={classification_result.fallback_reason}"
        )
        # 保留原始决策，不做任何改写
        state["intent_result"] = classification_result
        logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成 ===")
        return state

    # 问题4修复: 只有 ACCEPT 才进入任务管理
    # 不再尝试调用 BusinessIntent(None) 导致 ValueError
    if classification_result.decision != IntentDecision.ACCEPT or not classification_result.intent:
        logger.warning(
            f"[{turn_id}] ⚠️ 意图未被接受: decision={classification_result.decision.value}, "
            f"intent={classification_result.intent}"
        )
        state["intent_result"] = classification_result
        logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成 ===")
        return state

    # 映射到 BusinessIntent
    intent = classification_result.intent
    recognized = True
    logger.info(
        f"[{turn_id}] 🎯 Intent 识别结果: {intent.value}, "
        f"confidence={classification_result.confidence:.2f}"
    )

    # P1-06 修复问题 2：ActionMode 必须基于 IntentPolicy，不能硬编码
    # urge_order_payment 的 requires_action_request=False，不应进入 ACTION_REQUEST
    policy = get_intent_policy(intent)
    if policy.requires_action_request:
        action_mode = ActionMode.ACTION_REQUEST
    else:
        action_mode = ActionMode.INFORMATIONAL

    # 使用分类器返回的完整 IntentResult，只更新 action_mode
    intent_result = IntentResult(
        recognized=True,
        intent=intent,
        decision=IntentDecision.ACCEPT,
        confidence=classification_result.confidence,
        second_confidence=classification_result.second_confidence,
        margin=classification_result.margin,
        entities=classification_result.entities or {},
        action_mode=action_mode,
    )

    state["intent_result"] = intent_result

    # ===== Task 管理逻辑 =====
    # P1-48 修复：闲聊不启动新任务，保留原 active_task
    if intent == BusinessIntent.CHITCHAT:
        active_task = state.get("active_task")
        if active_task:
            # P0 修复: 处理从 Redis 恢复的 LangChain 序列化格式
            if isinstance(active_task, dict):
                from customer_service.tasking.models import TaskFrame
                # 检查是否是 LangChain 序列化格式 (包含 'lc', 'type', 'kwargs')
                if 'kwargs' in active_task and 'lc' in active_task:
                    active_task = TaskFrame(**active_task['kwargs'])
                else:
                    active_task = TaskFrame(**active_task)
                state["active_task"] = active_task

            # 有活跃任务时，闲聊不打断，直接返回
            logger.info(
                f"[{turn_id}] 💬 检测到闲聊插话，保留原任务: {active_task.intent}"
            )
            # 不调用 TaskContextManager，直接返回
            # ResponseGen 会根据 CHITCHAT intent 生成简短回复
            return state
        else:
            # 没有活跃任务时，可以启动闲聊任务（首次对话场景）
            logger.info(f"[{turn_id}] 💬 首次对话闲聊，启动闲聊任务")
            state = TaskContextManager.start_task(
                state,
                intent=intent,
                turn_id=turn_id,
            )
            return state

    logger.info(
        f"[{turn_id}] ✅ 识别意图: {intent.value}, "
        f"confidence={classification_result.confidence:.2f}, "
        f"action_mode={action_mode.value if action_mode else 'None'}"
    )

    active_task = state.get("active_task")

    if not active_task:
        # 没有 active_task，启动新任务
        state = TaskContextManager.start_task(
            state,
            intent=intent_result.intent,
            turn_id=turn_id,
        )
        logger.info(f"[{turn_id}] 🆕 启动新任务: {intent_result.intent}")
    else:
        # P0 修复: 处理从 Redis 恢复的 LangChain 序列化格式
        if isinstance(active_task, dict):
            from customer_service.tasking.models import TaskFrame
            # 检查是否是 LangChain 序列化格式 (包含 'lc', 'type', 'kwargs')
            if 'kwargs' in active_task and 'lc' in active_task:
                active_task = TaskFrame(**active_task['kwargs'])
            else:
                active_task = TaskFrame(**active_task)
            state["active_task"] = active_task

        # 有 active_task
        if active_task.intent == intent_result.intent:
            # 继续当前任务
            state = TaskContextManager.continue_current(state, turn_id)
            logger.info(f"[{turn_id}] ➡️ 继续当前任务: {active_task.intent}")
        else:
            # 不同意图，暂停当前任务并启动新任务
            state = TaskContextManager.start_task(
                state,
                intent=intent_result.intent,
                turn_id=turn_id,
            )
            logger.info(
                f"[{turn_id}] 🔄 切换任务: "
                f"{active_task.intent} → {intent_result.intent}"
            )

    logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成 ===")
    return state


def _parse_intent_selection(user_message: str, candidate_intents: list[BusinessIntent]) -> BusinessIntent | None:
    """
    P1-21: 解析用户对多意图的选择

    支持的选择方式：
    - 数字序号：1、2、第一个、第二个
    - 意图名称：商品查询、尺码推荐等

    Args:
        user_message: 用户输入
        candidate_intents: 候选意图列表

    Returns:
        选中的意图，如果无法解析则返回 None
    """
    message = user_message.strip().lower()

    # 方式1：数字序号（1、2、3...）
    if message.isdigit():
        idx = int(message) - 1  # 转换为 0-based index
        if 0 <= idx < len(candidate_intents):
            return candidate_intents[idx]

    # 方式2：中文序号
    ordinal_map = {
        "第一": 0, "第一个": 0, "1": 0, "一": 0,
        "第二": 1, "第二个": 1, "2": 1, "二": 1,
        "第三": 2, "第三个": 2, "3": 2, "三": 2,
    }
    for key, idx in ordinal_map.items():
        if key in message and idx < len(candidate_intents):
            return candidate_intents[idx]

    # 方式3：意图名称关键词匹配
    intent_keywords = {
        BusinessIntent.PRODUCT_QUERY: ["商品", "产品", "推荐", "查询", "搜索"],
        BusinessIntent.SIZE_RECOMMEND: ["尺码", "尺寸", "码数", "大小"],
        BusinessIntent.URGE_ORDER_PAYMENT: ["催拍", "催付", "下单", "付款"],
        BusinessIntent.URGE_SHIPPING: ["催发货", "发货", "催单"],
        BusinessIntent.PROMOTION_QUERY: ["优惠", "促销", "活动", "折扣"],
        BusinessIntent.LOGISTICS_QUERY: ["物流", "快递", "配送"],
        BusinessIntent.RETURN: ["退货", "退款"],
        BusinessIntent.EXCHANGE: ["换货", "调换"],
        BusinessIntent.CHITCHAT: ["闲聊", "聊天"],
    }

    for intent in candidate_intents:
        keywords = intent_keywords.get(intent, [])
        if any(keyword in message for keyword in keywords):
            return intent

    return None


def _is_cancel_request(user_message: str) -> bool:
    """
    P1-22: 检测用户是否想取消当前任务

    取消关键词：算了、不要了、取消、停止、不用了、退出等

    Args:
        user_message: 用户输入

    Returns:
        是否是取消请求
    """
    message = user_message.strip().lower()

    cancel_keywords = [
        "算了", "不要了", "取消", "停止", "不用了",
        "退出", "不想要", "不需要", "放弃",
        "cancel", "stop", "quit", "exit"
    ]

    # 简单关键词匹配
    return any(keyword in message for keyword in cancel_keywords)
