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
from customer_service.graph.context_resolver import ContextResolver, ContextResolution  # P2修复：导入Context Resolver
from customer_service.intents.models import (
    BusinessIntent,
    IntentFallbackReason,
    TurnAction,
    IntentClassificationResult,
    TurnDecision,
    HybridIntentResult,  # NLU_HYBRID_REFACTOR
)
from customer_service.intents.policies import get_intent_policy
from customer_service.tasking.models import PendingIntentSelection
from customer_service.intents.classifier import IntentClassifier, adapt_intent_result_to_classification
from customer_service.intents.validator import IntentDecisionValidator
from customer_service.tasking.command_processor import TaskCommandProcessor
from customer_service.prompts.history_builder import HistoryBuilder


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

    # ===== 参考代码3修复: 状态优先解释层 =====
    # 优先级顺序（参考 E-commerce-AI-Agent-main/orchestrator._safe_route）：
    # 1. 取消请求（最高优先级）
    # 2. pending_intent_selection（多意图选择）
    # 3. WAITING_SLOT（等待槽位填充）
    # 4. 常规意图识别

    active_task = state.get("active_task")
    pending_selection = state.get("pending_intent_selection")

    # P0 修复：处理从 Redis 恢复的 LangChain 序列化格式
    if active_task and isinstance(active_task, dict):
        from customer_service.tasking.models import TaskFrame
        if 'kwargs' in active_task and 'lc' in active_task:
            active_task = TaskFrame(**active_task['kwargs'])
            state["active_task"] = active_task  # 更新为对象
        elif 'task_id' in active_task:  # 普通字典格式
            active_task = TaskFrame(**active_task)
            state["active_task"] = active_task

    # 优先级1: 取消请求
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

        # 阶段1修复：使用TurnAction枚举
        state["turn_action"] = TurnAction.CANCEL

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

    # 优先级2: pending_intent_selection（多意图选择）
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

            # 阶段1修复：使用TurnAction枚举
            state["turn_action"] = TurnAction.ACCEPT

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

            # 阶段1修复：使用TurnAction枚举
            state["turn_action"] = TurnAction.SELECT_INTENT

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

    # ===== 优先级3: WAITING_SLOT 状态优先解释（参考代码3）=====
    # 参考 E-commerce-AI-Agent-main/orchestrator._safe_route
    # 文档第121行："刚问'想查哪款商品的优惠'，用户回复'15970'，应先进入促销 Task 的商品槽位校验"
    #
    # 核心原则：当前任务等待槽位时，短输入优先解析为槽位填充，而不是新意图
    from customer_service.graph.state import TaskStatus

    if active_task and active_task.status == TaskStatus.WAITING_SLOT:
        logger.info(f"[{turn_id}] 🔄 当前任务正在等待槽位，优先尝试补槽")

        # 检查是否是明确的新业务目标（通过关键词判断）
        if _is_new_explicit_goal(current_message):
            logger.info(f"[{turn_id}] 🆕 检测到明确的新业务目标，切换任务")
            # 继续走正常分类流程
        else:
            # 尝试解析为槽位回答
            slot_filled = _try_fill_missing_slots(state, active_task, current_message, turn_id)

            if slot_filled:
                logger.info(f"[{turn_id}] ✅ 成功补充槽位，继续当前任务")
                state["turn_action"] = TurnAction.ACCEPT

                # 构造 IntentResult（继续当前任务）
                intent_result = IntentResult(
                    recognized=True,
                    intent=active_task.intent,
                    decision=IntentDecision.ACCEPT,
                    confidence=1.0,
                    entities=active_task.slots,
                )
                state["intent_result"] = intent_result

                # 使用 CommandProcessor 继续任务
                processor = TaskCommandProcessor()
                from customer_service.tasking.commands import ContinueTaskCommand
                state = processor.run(state, [ContinueTaskCommand()], turn_id)

                logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（补槽成功）===")
                return state
            else:
                logger.info(f"[{turn_id}] ⚠️ 无法解析为槽位回答，走正常分类流程")
                # 继续走正常分类流程

    # ===== P1修复：优先检测历史查询（参考修改建议1第十一节）=====
    # "我刚问了什么？"这类query是对话元查询，不需要走业务Intent分类
    if _is_history_query(current_message):
        logger.info(f"[{turn_id}] 📜 检测到历史查询，直接响应")

        # 获取历史对话
        history_str = await _get_conversation_history(state, config, turn_id)

        if history_str:
            # 提取最近一条用户消息
            last_user_message = _extract_last_user_message(history_str)
            if last_user_message:
                response = f"你刚才问的是：「{last_user_message}」"
            else:
                response = "这是我们对话的开始，您还没有问过其他问题～"
        else:
            response = "这是我们对话的开始，您还没有问过其他问题～"

        # 直接设置响应，不走Intent分类
        state["turn_action"] = TurnAction.CHITCHAT  # 历史查询视为类似闲聊的元对话
        state["intent_result"] = IntentResult(
            recognized=False,  # 不是业务Intent
            intent=None,
            decision=IntentDecision.ACCEPT,
            confidence=1.0,
            entities={}
        )
        state["response_draft"] = response

        logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（历史查询）===")
        return state

    # ===== NLU_HYBRID_REFACTOR：混合NLU三层架构 =====
    # 流程：Context Resolver → classify_hybrid（Rule + LLM Hybrid）→ Validator → TurnAction
    # P1-40修复：从数据库获取历史对话
    # P0修复：必须传入config参数以获取runtime.session_id
    # P2修复（修改建议2第十节）：先调用Context Resolver解析上下文

    # 获取历史对话
    history_str = await _get_conversation_history(state, config, turn_id)

    # ===== P2修复：Context Resolver（规则优先）=====
    from customer_service.graph.task_context_manager import _ensure_dialogue_frame

    dialogue_frame = _ensure_dialogue_frame(state)
    active_task = state.get("active_task")

    resolver = ContextResolver()
    context_resolution = resolver.resolve(
        current_message=current_message,
        dialogue_frame=dialogue_frame,
        active_task=active_task,
        turn_id=turn_id,
    )

    logger.info(
        f"[{turn_id}] 📍 Context解析: mode={context_resolution.mode}, "
        f"inherited_intent={context_resolution.inherited_intent.value if context_resolution.inherited_intent else 'None'}, "
        f"confidence={context_resolution.confidence:.2f}"
    )
    if context_resolution.reasoning:
        logger.info(f"[{turn_id}] 💡 推理: {context_resolution.reasoning}")

    # P0-1修复：如果ContextResolver已经确定意图继承，直接使用，跳过classify_hybrid
    if context_resolution.mode == "repeat_last_intent" and context_resolution.inherited_intent:
        logger.info(
            f"[{turn_id}] ✅ ContextResolver已确定意图继承，跳过classify_hybrid "
            f"intent={context_resolution.inherited_intent.value}"
        )

        # 获取IntentPolicy（使用已导入的函数）
        policy = get_intent_policy(context_resolution.inherited_intent)
        action_mode = ActionMode.ACTION_REQUEST if policy.requires_action_request else ActionMode.INFORMATIONAL

        # 直接构造IntentResult
        old_result = IntentResult(
            recognized=True,
            intent=context_resolution.inherited_intent,
            decision=IntentDecision.ACCEPT,
            confidence=context_resolution.confidence,
            entities=context_resolution.entity_updates,
            action_mode=action_mode,
            inherited=True,  # 标记为继承的意图
        )

        # 跳转到验证器（第3层）
        classification: IntentClassificationResult = adapt_intent_result_to_classification(
            old_result,
            current_message
        )
        validator = IntentDecisionValidator()
        decision: TurnDecision = validator.validate(state, classification)

        logger.info(
            f"[NLU] [{turn_id}] turn_action={decision.action.value} (inherited)"
        )

        state["turn_action"] = decision.action

        # 处理决策（复用后面的决策处理逻辑）
        # 因为是继承意图，直接接受
        if decision.action == TurnAction.ACCEPT and decision.accepted_goal:
            intent = decision.accepted_goal.intent
            entities = decision.accepted_goal.entities

            state["intent_result"] = IntentResult(
                recognized=True,
                intent=intent,
                decision=IntentDecision.ACCEPT,
                confidence=context_resolution.confidence,
                entities=entities,
                action_mode=action_mode,
                inherited=True,
            )

            # 使用 CommandProcessor 执行命令
            if decision.commands:
                processor = TaskCommandProcessor()
                state = processor.run(state, decision.commands, turn_id)
                logger.info(f"[{turn_id}] 🔧 执行了 {len(decision.commands)} 条命令")

            logger.info(f"[{turn_id}] === 节点 1: Intent Parse 完成（继承意图）===")
            return state
        else:
            # 如果验证器拒绝了继承的意图，继续走正常分类流程
            logger.warning(f"[{turn_id}] ⚠️ 验证器拒绝继承意图，继续走正常分类")

    # 获取当前活跃意图（用于意图继承）
    active_intent = context_resolution.inherited_intent or (active_task.intent if active_task else None)
    logger.info(f"[{turn_id}] 当前活跃意图: {active_intent.value if active_intent else '无'}")

    # ===== NLU_HYBRID_REFACTOR：构建 NLU 上下文（传给 LLM Classifier）=====
    # P0-2修复：添加focused_object到nlu_context
    # 阶段2-任务4：完善nlu_context结构，参考TurnPlanner
    nlu_context: dict = {
        "active_task_intent": active_intent.value if active_intent else None,
        "active_task_status": active_task.status.value if active_task and hasattr(active_task, "status") else None,
        "missing_slots": getattr(active_task, "missing_slots", None) if active_task else None,
        "conversation_focus": (
            f"{context_resolution.inherited_intent.value}" if context_resolution.inherited_intent else None
        ),
        "last_business_intent": (
            dialogue_frame.last_business_intent.value
            if dialogue_frame and getattr(dialogue_frame, "last_business_intent", None)
            else None
        ),
    }

    # P0-2修复：传递focused_object（从dialogue_frame.last_focus获取）
    if dialogue_frame and hasattr(dialogue_frame, "last_focus") and dialogue_frame.last_focus:
        focus = dialogue_frame.last_focus
        nlu_context["focused_object"] = {
            "entity_type": focus.entity_type,
            "entity_id": focus.entity_id,
        }
        logger.info(
            f"[{turn_id}] 📌 Focused Object: {focus.entity_type}={focus.entity_id}"
        )

    # P0-2修复：传递paused_tasks（如果有）
    paused_tasks = state.get("paused_tasks", [])
    if paused_tasks:
        paused_intents = [
            task.intent.value if hasattr(task, "intent") else None
            for task in paused_tasks
        ]
        nlu_context["paused_tasks"] = [i for i in paused_intents if i]
        logger.info(f"[{turn_id}] ⏸️ Paused Tasks: {nlu_context['paused_tasks']}")

    # 阶段2-任务4：传递available_intents列表（让LLM知道系统支持哪些意图）
    from customer_service.intents.validator import SUPPORTED_INTENTS
    nlu_context["available_intents"] = [intent.value for intent in SUPPORTED_INTENTS]

    # 阶段2-任务4：传递完整的active_task信息（而非只传intent）
    if active_task:
        nlu_context["active_task_full"] = {
            "intent": active_task.intent.value if hasattr(active_task, "intent") else None,
            "status": active_task.status.value if hasattr(active_task, "status") else None,
            "slots": getattr(active_task, "slots", {}),
            "missing_slots": getattr(active_task, "missing_slots", []),
        }

    # 阶段2-任务4：传递完整的paused_tasks信息
    if paused_tasks:
        nlu_context["paused_tasks_full"] = [
            {
                "intent": task.intent.value if hasattr(task, "intent") else None,
                "status": task.status.value if hasattr(task, "status") else None,
            }
            for task in paused_tasks
            if hasattr(task, "intent")
        ]

    # 从 Context Resolver 继承的实体作为上下文实体候选
    if context_resolution.entity_updates:
        from customer_service.intents.entity_fusion import rule_entities_to_candidates
        ctx_entity_candidates = rule_entities_to_candidates(
            context_resolution.entity_updates, base_confidence=0.80
        )
        nlu_context["context_entity_candidates"] = ctx_entity_candidates

    # ===== 第1层：Hybrid NLU 分类（Rule + LLM）=====
    # NLU_HYBRID_REFACTOR：使用 classify_hybrid 替代旧的 classify
    # 注意：use_llm=True 才会真正调用 LLM；生产环境可从配置读取
    from customer_service.config.config import settings as app_settings
    use_llm_flag = getattr(app_settings, "nlu_use_llm", False)

    classifier = IntentClassifier(use_llm=use_llm_flag)
    hybrid_result = await classifier.classify_hybrid(
        current_message,
        history=history_str,
        context=nlu_context,
        active_intent=active_intent,
    )

    # NLU_HYBRID_REFACTOR：结构化可观测日志（第20节要求）
    _rule_conf_str = f"{hybrid_result.rule_confidence:.3f}" if hybrid_result.rule_confidence is not None else "0.000"
    _margin_str = f"{hybrid_result.margin:.3f}" if hybrid_result.margin is not None else "0.000"
    _llm_conf_str = f"{hybrid_result.llm_confidence:.3f}" if hybrid_result.llm_confidence is not None else "0.000"
    logger.info(
        f"[NLU] [{turn_id}]\n"
        f"  rule_intent={hybrid_result.rule_intent.value if hybrid_result.rule_intent else 'None'}\n"
        f"  rule_confidence={_rule_conf_str}\n"
        f"  margin={_margin_str}\n"
        f"  llm_called={hybrid_result.llm_called}\n"
        f"  llm_intent={hybrid_result.llm_intent.value if hybrid_result.llm_intent else 'None'}\n"
        f"  llm_confidence={_llm_conf_str}\n"
        f"  entity_sources={{{', '.join(f'{k}:{v.source}' for k, v in hybrid_result.entities.items())}}}\n"
        f"  final_intent={hybrid_result.intent.value if hybrid_result.intent else 'None'}\n"
        f"  final_confidence={hybrid_result.confidence:.3f}\n"
        f"  source={hybrid_result.source}\n"
        f"  ambiguous={hybrid_result.ambiguous}"
    )

    # ===== 第2层：将 HybridIntentResult 转换为旧 IntentResult（向后兼容）=====
    # NLU_HYBRID_REFACTOR：HybridResult → old_result → adapt_intent_result_to_classification
    # 保持 Validator 不变，只替换 NLU 层
    if hybrid_result.ambiguous and hybrid_result.intent is None:
        # 意图歧义/冲突 → CLARIFY（模拟旧的多意图路径）
        old_result = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLARIFY,
            fallback_reason=IntentFallbackReason.MULTIPLE_INTENTS,
            confidence=hybrid_result.confidence,
            entities=hybrid_result.to_entities_dict(),
        )
    elif hybrid_result.is_out_of_scope:
        old_result = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.OUT_OF_SCOPE,
            confidence=hybrid_result.confidence,
            entities=hybrid_result.to_entities_dict(),
        )
    elif hybrid_result.intent is None:
        old_result = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLARIFY,
            fallback_reason=IntentFallbackReason.LOW_CONFIDENCE,
            confidence=hybrid_result.confidence,
            entities=hybrid_result.to_entities_dict(),
        )
    else:
        old_result = IntentResult(
            recognized=True,
            intent=hybrid_result.intent,
            decision=IntentDecision.ACCEPT,
            confidence=hybrid_result.confidence,
            margin=hybrid_result.margin,
            entities=hybrid_result.to_entities_dict(),
        )

    # 合并Context Resolver提取的实体更新（已经在 nlu_context 里参与了融合，这里兜底更新）
    if context_resolution.entity_updates:
        old_result.entities.update(context_resolution.entity_updates)

    # ===== 第3层：适配器 → 验证器 → TurnAction =====
    classification: IntentClassificationResult = adapt_intent_result_to_classification(
        old_result,
        current_message
    )

    # 第3层：验证器 - 根据规则决策
    validator = IntentDecisionValidator()
    decision: TurnDecision = validator.validate(state, classification)

    logger.info(
        f"[NLU] [{turn_id}] turn_action={decision.action.value} "
        f"missing_slots={getattr(active_task, 'missing_slots', None)}"
    )

    # ===== 根据 TurnDecision.action 设置 turn_action 和状态 =====
    state["turn_action"] = decision.action

    # 处理不同的决策动作
    if decision.action == TurnAction.CLASSIFIER_FAILURE:
        # 分类器失败
        state["intent_result"] = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLASSIFIER_FAILURE,
            confidence=0.0,
            entities={},
        )
        logger.warning(f"[{turn_id}] ❌ 分类器失败: {decision.reason}")
        return state

    elif decision.action == TurnAction.OUT_OF_SCOPE:
        # 超出范围
        state["intent_result"] = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.OUT_OF_SCOPE,
            confidence=0.0,
            entities={},
        )
        logger.info(f"[{turn_id}] 🚫 超出范围: {decision.reason}")
        return state

    elif decision.action == TurnAction.CLARIFY:
        # 需要澄清（低置信度）
        state["intent_result"] = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLARIFY,
            fallback_reason=IntentFallbackReason.LOW_CONFIDENCE,
            confidence=0.5,
            entities={},
        )
        logger.info(f"[{turn_id}] ❓ 需要澄清: {decision.reason}")
        return state

    elif decision.action == TurnAction.SELECT_INTENT:
        # 多目标，需要用户选择
        if not decision.clarify_options or len(decision.clarify_options) < 2:
            logger.error(f"[{turn_id}] ⚠️ SELECT_INTENT但缺少clarify_options")
            state["turn_action"] = TurnAction.CLARIFY
            state["intent_result"] = IntentResult(
                recognized=False,
                intent=None,
                decision=IntentDecision.CLARIFY,
                confidence=0.0,
                entities={},
            )
            return state

        # 创建 pending_intent_selection
        candidate_intents = [goal.intent for goal in decision.clarify_options]
        state["pending_intent_selection"] = PendingIntentSelection(
            candidate_intents=candidate_intents,
            original_turn_id=turn_id,
        )

        state["intent_result"] = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLARIFY,
            fallback_reason=IntentFallbackReason.MULTIPLE_INTENTS,
            confidence=0.8,
            candidate_intents=candidate_intents,
            entities={},
        )
        logger.info(f"[{turn_id}] 🔀 多目标: {[i.value for i in candidate_intents]}")
        return state

    elif decision.action == TurnAction.UNSUPPORTED:
        # 识别了但未开放
        state["intent_result"] = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLARIFY,
            confidence=0.7,
            entities={},
        )
        logger.info(f"[{turn_id}] 🚧 功能未开放: {decision.reason}")
        return state

    elif decision.action == TurnAction.CHITCHAT:
        # 闲聊 - 不启动任务
        if not decision.accepted_goal:
            logger.error(f"[{turn_id}] ⚠️ CHITCHAT但缺少accepted_goal")
            state["turn_action"] = TurnAction.CLARIFY
            return state

        intent = decision.accepted_goal.intent
        entities = decision.accepted_goal.entities

        state["intent_result"] = IntentResult(
            recognized=True,
            intent=intent,
            decision=IntentDecision.ACCEPT,
            confidence=decision.accepted_goal.confidence or 0.8,
            entities=entities,
            action_mode=ActionMode.INFORMATIONAL,
        )

        # 闲聊不启动任务（参考文档 P0-6）
        logger.info(f"[{turn_id}] 💬 闲聊，不启动任务")
        return state

    elif decision.action == TurnAction.ACCEPT:
        # 接受目标 - 使用 CommandProcessor 执行命令
        if not decision.accepted_goal:
            logger.error(f"[{turn_id}] ⚠️ ACCEPT但缺少accepted_goal")
            state["turn_action"] = TurnAction.CLARIFY
            return state

        intent = decision.accepted_goal.intent
        entities = decision.accepted_goal.entities

        # 获取 IntentPolicy
        policy = get_intent_policy(intent)
        action_mode = ActionMode.ACTION_REQUEST if policy.requires_action_request else ActionMode.INFORMATIONAL

        state["intent_result"] = IntentResult(
            recognized=True,
            intent=intent,
            decision=IntentDecision.ACCEPT,
            confidence=decision.accepted_goal.confidence or 0.8,
            entities=entities,
            action_mode=action_mode,
        )

        # 使用 CommandProcessor 执行命令（阶段1重构）
        if decision.commands:
            processor = TaskCommandProcessor()
            state = processor.run(state, decision.commands, turn_id)
            logger.info(f"[{turn_id}] 🔧 执行了 {len(decision.commands)} 条命令")
        else:
            # 兼容：如果验证器没有生成命令，回退到旧逻辑
            state = TaskContextManager.start_task(
                state,
                intent=intent,
                turn_id=turn_id,
            )
            logger.info(f"[{turn_id}] 🆕 启动任务（旧逻辑）: {intent.value}")

        return state

    else:
        # 未知 action
        logger.error(f"[{turn_id}] ❌ 未知的 TurnAction: {decision.action}")
        state["turn_action"] = TurnAction.CLARIFY
        state["intent_result"] = IntentResult(
            recognized=False,
            intent=None,
            decision=IntentDecision.CLASSIFIER_FAILURE,
            confidence=0.0,
            entities={},
        )
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


def _is_new_explicit_goal(message: str) -> bool:
    """
    阶段2修复：检测用户消息是否是明确的新业务目标

    根据文档第194行："若这轮明确提出新的完整业务目标，才挂起旧任务并切换"

    判断标准：
    - 包含明确的业务关键词（推荐、查询、优惠、物流等）
    - 不是单纯的数字、颜色、价格回答

    Args:
        message: 用户消息

    Returns:
        是否是明确的新目标
    """
    message = message.strip()

    # 单纯的短回复（数字、颜色、确认词）不是新目标
    if len(message) <= 10:
        # 纯数字或带单位的数字
        if message.replace(" ", "").replace("元", "").replace("以内", "").replace(".", "").isdigit():
            return False
        # 颜色词
        if message in ["红色", "黑色", "白色", "蓝色", "绿色", "黄色", "第一个", "第二个", "第三个"]:
            return False
        # 确认词
        if message in ["是", "好的", "确认", "对", "嗯", "ok", "可以"]:
            return False

    # 包含明确业务关键词的才算新目标
    goal_keywords = [
        "推荐", "查", "看", "搜索", "找", "要", "买", "购买",
        "优惠", "促销", "折扣", "活动",
        "物流", "发货", "快递", "订单",
        "退货", "换货", "退款",
        "尺码", "大小", "型号"
    ]

    return any(keyword in message for keyword in goal_keywords)


def _try_fill_missing_slots(
    state: AgentState,
    task: any,
    message: str,
    turn_id: str
) -> bool:
    """
    阶段2修复：智能槽位补填 - 解决P0-4问题

    根据文档第39行："用户说'预算500，商品15970'，第一个数字是 500；
    说'15970和39386哪款有优惠'，又会在需要唯一商品时任取 15970"

    改进策略：
    - 区分价格、商品编号、序数指代
    - 多个疑似编号时不自动选择，返回False让系统询问
    - 带单位的数字优先解析为价格

    Args:
        state: Agent状态
        task: 当前任务
        message: 用户消息
        turn_id: 轮次ID

    Returns:
        是否成功补充槽位
    """
    import re
    from customer_service.tasking.models import TaskFrame, TaskStatus

    if not task.missing_slots:
        return False

    # 确保 task 是 TaskFrame 对象
    if isinstance(task, dict):
        task = TaskFrame(**task.get("kwargs", task))
        state["active_task"] = task

    message = message.strip()
    logger.info(f"[{turn_id}] 🔍 尝试从 '{message}' 中提取槽位: {task.missing_slots}")

    # 提取所有数字
    numbers = re.findall(r'\d+', message)

    if not numbers:
        logger.info(f"[{turn_id}] ⚠️ 消息中没有数字")
        return False

    # === 补充 product_id ===
    if "product_id" in task.missing_slots:
        # 检查是否是价格表达（带"元"、"预算"、"以内"等）
        if any(keyword in message for keyword in ["元", "预算", "以内", "左右", "块钱"]):
            logger.info(f"[{turn_id}] ⚠️ 检测到价格关键词，不解析为商品编号")
            return False

        # 检查是否有多个疑似编号
        # 商品编号通常是4-6位数字
        product_ids = [n for n in numbers if len(n) >= 4 and len(n) <= 6]

        if len(product_ids) == 0:
            logger.info(f"[{turn_id}] ⚠️ 没有找到符合商品编号格式的数字（4-6位）")
            return False

        if len(product_ids) > 1:
            logger.info(f"[{turn_id}] ⚠️ 发现多个疑似商品编号 {product_ids}，需要用户明确选择")
            return False

        # 唯一编号，验证并填充
        product_id = product_ids[0]
        task.slots["product_id"] = product_id
        task.missing_slots.remove("product_id")
        logger.info(f"[{turn_id}] ✅ 成功提取 product_id={product_id}")
        return True

    # === 补充 order_id ===
    if "order_id" in task.missing_slots:
        # 订单号通常更长（8位以上）
        order_ids = [n for n in numbers if len(n) >= 8]

        if len(order_ids) == 0:
            logger.info(f"[{turn_id}] ⚠️ 没有找到符合订单号格式的数字（≥8位）")
            return False

        if len(order_ids) > 1:
            logger.info(f"[{turn_id}] ⚠️ 发现多个疑似订单号 {order_ids}，需要用户明确选择")
            return False

        order_id = order_ids[0]
        task.slots["order_id"] = order_id
        task.missing_slots.remove("order_id")
        logger.info(f"[{turn_id}] ✅ 成功提取 order_id={order_id}")
        return True

    return False


async def _get_conversation_history(
    state: AgentState,
    config: RunnableConfig,
    turn_id: str,
) -> str:
    """
    从数据库获取历史对话

    P0修复（参考修改建议1第九、十节）：
    1. 从 config.runtime.session_id 获取session_id（而非state）
    2. 排除当前turn_id的消息（避免"我刚问了什么"包含自己）
    3. 限制最近20条消息（10轮对话）

    Args:
        state: Agent状态
        config: LangGraph配置（包含runtime context）
        turn_id: 当前轮次ID

    Returns:
        格式化的历史对话字符串，如果无历史则返回空字符串
    """
    try:
        # P0修复：从config.runtime获取session_id和user_id
        configurable = config.get("configurable", {})
        runtime = configurable.get("runtime")

        if not runtime:
            logger.warning(f"[{turn_id}] ⚠️ runtime 缺失，跳过历史对话")
            return ""

        session_id = runtime.session_id
        user_id = runtime.principal.user_id

        if not session_id:
            logger.warning(f"[{turn_id}] ⚠️ session_id 缺失，跳过历史对话")
            return ""

        # 获取数据库会话
        from customer_service.infrastructure.database import get_db_session
        from customer_service.models.chat import ChatMessage
        from sqlalchemy import select

        async with get_db_session() as db_session:
            # P0修复：排除当前turn_id，避免"我刚问了什么"包含自己
            stmt = (
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.user_id == user_id,
                    ChatMessage.turn_id != turn_id,  # 关键：排除当前turn
                )
                .order_by(ChatMessage.created_at.desc())
                .limit(20)
            )
            result = await db_session.execute(stmt)
            messages = list(result.scalars().all())

            if not messages:
                logger.info(f"[{turn_id}] 📜 当前会话无历史消息")
                return ""

            # 反转顺序（从旧到新）
            messages.reverse()

            # 转换为字典格式
            message_dicts = []
            for msg in messages:
                message_dicts.append({
                    "role": msg.role.value if hasattr(msg.role, 'value') else msg.role,
                    "content": msg.content,
                })

            # 使用 HistoryBuilder 格式化
            history = HistoryBuilder.build_from_messages(message_dicts, max_turns=20)

            logger.info(f"[{turn_id}] 📜 成功获取历史对话，共 {len(messages)} 条消息")
            return history

    except Exception as e:
        logger.error(f"[{turn_id}] ❌ 获取历史对话失败: {e}", exc_info=True)
        return ""


def _is_history_query(message: str) -> bool:
    """
    检测是否是历史查询（对话元查询）

    P1修复（参考修改建议1第十一节）：
    这类query询问的是对话本身，而非业务需求
    例如："我刚问了什么？"、"上一句我说了什么？"

    Args:
        message: 用户消息

    Returns:
        是否是历史查询
    """
    patterns = [
        "我刚问了什么",
        "我刚才问了什么",
        "我刚说了什么",
        "我刚才说了什么",
        "上一句我说了什么",
        "上一句我问了什么",
        "刚才我问的什么",
        "刚才我说的什么",
        "之前我问了什么",
        "之前我说了什么",
        "我问过什么",
        "刚才问了啥",
        "刚问了啥",
    ]

    message_lower = message.lower()
    return any(pattern in message_lower for pattern in patterns)


def _extract_last_user_message(history: str) -> str | None:
    """
    从历史对话中提取最近一条用户消息

    Args:
        history: 格式化的历史对话字符串（"USER: xxx\nASSISTANT: xxx"）

    Returns:
        最近一条用户消息内容，如果没有则返回None
    """
    if not history:
        return None

    lines = history.strip().split('\n')

    # 从后往前找最近的USER消息
    for line in reversed(lines):
        if line.startswith('USER:'):
            # 提取USER:后面的内容
            content = line[5:].strip()
            return content

    return None
