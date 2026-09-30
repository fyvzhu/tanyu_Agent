"""
LangGraph 节点 - Response Gen
根据 01_slice_foundation 文档 #13 定义

核心职责：
- 根据 Task 状态生成响应文本
- 处理 Tool Result
- 生成最终用户可见的消息

P1-07 修复：
- 统一处理 FlowResult 契约
- 所有 Flow 返回统一格式：ready_for_response, tool_result, dialogue_reason, objects
- 不再针对每个 Intent 特殊处理不同的返回格式

P0 架构修复：
- 接受 config 参数以符合 LangGraph 规范
- 当前不使用 runtime context，但保持签名一致性
"""
from __future__ import annotations

from loguru import logger
from langgraph.types import RunnableConfig

from customer_service.graph.state import AgentState, TaskStatus
from customer_service.intents.models import BusinessIntent
from customer_service.flows.models import FlowResult
from customer_service.infrastructure.llm import get_llm
from customer_service.prompts import render_prompt


async def response_gen_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    节点 4: Response Gen

    逻辑：
    1. 根据 Task 状态决定响应类型
    2. 如果是 WAITING_SLOT，生成补槽提示
    3. 如果是 READY/COMPLETED，生成最终响应
    4. 整合 Tool Result（如果有）

    Slice 01 版本：
    - CHITCHAT：生成友好回复
    - 其他 Intent：提示功能正在开发或引导用户
    """
    turn_id = state.get("turn_id", "unknown")
    active_task = state.get("active_task")
    current_message = state.get("current_message", "")

    logger.info(f"[{turn_id}] === 节点 4: Response Gen 开始 ===")

    # 问题4修复: 优先处理 pending_intent_selection 的展示
    pending_selection = state.get("pending_intent_selection")
    if pending_selection:
        # 展示候选意图供用户选择
        response_draft = _generate_intent_selection_prompt(pending_selection.candidate_intents)
        state["response_draft"] = response_draft
        logger.info(f"[{turn_id}] 🔀 生成多意图选择提示")
        logger.info(f"[{turn_id}] === 节点 4: Response Gen 完成（意图选择）===")
        return state

    # 问题6修复: 检查是否是本轮恢复的任务
    resumed_this_turn = state.get("resumed_this_turn", False)
    task_transition = state.get("task_transition")

    if resumed_this_turn:
        # 恢复任务时生成明确的提示
        response_draft = _generate_resume_task_prompt(state, task_transition)
        state["response_draft"] = response_draft
        logger.info(f"[{turn_id}] 🔄 生成任务恢复提示")
        logger.info(f"[{turn_id}] === 节点 4: Response Gen 完成（任务恢复）===")
        return state

    # 问题4修复: 检查是否是取消操作
    if not active_task:
        # 如果是刚取消的任务，生成取消确认
        if task_transition and task_transition.action == "cancel":
            response_draft = "好的，已为您取消当前操作。还有什么我可以帮您的吗？"
            state["response_draft"] = response_draft
            logger.info(f"[{turn_id}] ✅ 生成取消确认")
            return state

        # 其他没有任务的情况，fallback
        response_draft = "抱歉，我不太理解您的意思。您可以问我商品信息、促销活动或者订单相关的问题哦～"
        state["response_draft"] = response_draft
        state["fallback_used"] = True
        logger.warning(f"[{turn_id}] ⚠️ 没有 active_task，使用 fallback")
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

    # 问题6修复：检查是否是闲聊插话
    # 如果 intent_result 是 CHITCHAT 但 active_task 不是，说明是闲聊插话
    intent_result = state.get("intent_result")
    if (intent_result and
        intent_result.intent == BusinessIntent.CHITCHAT and
        active_task.intent != BusinessIntent.CHITCHAT):
        # 闲聊插话，使用闲聊响应
        response_draft = _generate_chitchat_response(current_message)
        state["response_draft"] = response_draft
        logger.info(f"[{turn_id}] 💬 闲聊插话，生成闲聊响应")
        return state

    # 检查 Task 状态
    task_status = active_task.status
    intent = active_task.intent

    # 如果是 WAITING_SLOT，生成澄清问题
    if task_status == TaskStatus.WAITING_SLOT:
        missing_slots = active_task.missing_slots
        response_draft = _generate_clarification(intent, missing_slots, current_message)
        state["response_draft"] = response_draft
        logger.info(f"[{turn_id}] ℹ️ 生成补槽澄清: missing_slots={missing_slots}")
        return state

    # P1-07 修复：统一处理 FlowResult
    flow_result = state.get("flow_result")

    logger.info(
        f"[{turn_id}] 开始生成响应, intent={intent.value}, "
        f"flow_result type={type(flow_result)}"
    )

    # 统一的 FlowResult 处理
    if flow_result and isinstance(flow_result, FlowResult):
        # 检查是否需要澄清
        if not flow_result.ready_for_response:
            if flow_result.dialogue_reason == "clarify":
                # 从 tool_result.data 提取澄清信息
                clarification = flow_result.tool_result.data.get("clarification", "请问您想了解什么呢？")
                state["response_draft"] = clarification
                logger.info(f"[{turn_id}] 📝 需要澄清: {clarification}")
                return state
            else:
                # 其他原因导致未准备好
                state["response_draft"] = "请问您想了解什么呢？"
                return state

        # 检查是否有错误
        if flow_result.dialogue_reason == "error":
            error_msg = "抱歉，查询时遇到了一些问题。您可以稍后再试～"
            state["response_draft"] = error_msg
            state["fallback_used"] = True
            logger.warning(f"[{turn_id}] ❌ Flow 执行出错")
            return state

        # 成功：根据 Intent 生成响应
        response_draft = await _generate_response_from_flow_result(
            intent=intent,
            flow_result=flow_result,
            current_message=current_message,
            turn_id=turn_id
        )
    else:
        # 兼容旧格式或无 flow_result 的情况
        if intent == BusinessIntent.CHITCHAT:
            response_draft = _generate_chitchat_response(current_message)
        elif intent == BusinessIntent.SIZE_RECOMMEND:
            response_draft = "尺码推荐功能正在开发中，您可以先查看商品详情页的尺码表哦～"
        elif intent == BusinessIntent.LOGISTICS_QUERY:
            response_draft = "物流查询功能正在开发中，您可以先在订单详情页查看物流信息～"
        elif intent == BusinessIntent.RETURN:
            response_draft = "退货申请功能正在开发中，请先联系客服人工处理～"
        elif intent == BusinessIntent.EXCHANGE:
            response_draft = "换货申请功能正在开发中，请先联系客服人工处理～"
        elif intent == BusinessIntent.URGE_SHIPPING:
            response_draft = "催发货功能正在开发中，您可以先在订单详情页查看发货状态～"
        else:
            response_draft = "抱歉，我暂时无法处理这个请求。您可以换个方式问我，或者联系人工客服～"
            state["fallback_used"] = True

    state["response_draft"] = response_draft

    logger.info(
        f"[{turn_id}] === 节点 4: Response Gen 完成 === "
        f"intent={intent.value}, response_length={len(response_draft)}"
    )

    return state


async def _generate_response_from_flow_result(
    intent: BusinessIntent,
    flow_result: FlowResult,
    current_message: str,
    turn_id: str,
) -> str:
    """
    P1-07 修复：统一从 FlowResult 生成响应

    不再针对每个 Intent 特殊处理不同格式，而是统一处理 FlowResult
    """
    if intent == BusinessIntent.PRODUCT_QUERY:
        return _generate_product_response_from_flow(flow_result, current_message, turn_id)
    elif intent == BusinessIntent.PROMOTION_QUERY:
        return _generate_promotion_response_from_flow(flow_result, current_message, turn_id)
    elif intent == BusinessIntent.URGE_ORDER_PAYMENT:
        return await _generate_conversion_response_from_flow(flow_result, current_message, turn_id)
    else:
        return "抱歉，我暂时无法处理这个请求～"


def _generate_intent_selection_prompt(candidate_intents: list) -> str:
    """
    问题4修复：生成多意图选择提示

    示例输出:
    "您好！我理解您可能想要：
    1. 查询商品信息
    2. 查询促销活动
    请回复数字选择，或重新描述您的需求～"
    """
    from customer_service.tasking.models import BusinessIntent

    # 意图名称映射
    intent_names = {
        BusinessIntent.PRODUCT_QUERY: "查询商品信息",
        BusinessIntent.PROMOTION_QUERY: "查询促销活动",
        BusinessIntent.SIZE_RECOMMEND: "获取尺码推荐",
        BusinessIntent.LOGISTICS_QUERY: "查询订单物流",
        BusinessIntent.RETURN: "申请退货",
        BusinessIntent.EXCHANGE: "申请换货",
        BusinessIntent.URGE_ORDER_PAYMENT: "催付订单",
        BusinessIntent.CHITCHAT: "闲聊",
    }

    lines = ["您好！我理解您可能想要："]
    for i, intent in enumerate(candidate_intents, 1):
        intent_name = intent_names.get(intent, intent.value)
        lines.append(f"{i}. {intent_name}")
    lines.append("请回复数字选择，或重新描述您的需求～")

    return "\n".join(lines)


def _generate_clarification(intent: BusinessIntent, missing_slots: list[str], message: str) -> str:
    """
    问题5修复：生成针对具体意图的补槽澄清问题

    按照文档要求，每个意图应该有明确的补槽问题，让用户知道应该提供什么信息
    """
    if not missing_slots:
        return "请问您想了解什么呢？"

    # 问题5修复：根据意图类型和缺失槽位生成明确的澄清问题
    if intent == BusinessIntent.PROMOTION_QUERY:
        if "product_id" in missing_slots:
            return "请问您想查询哪件商品的优惠活动呢？请提供商品编号或名称～"

    elif intent == BusinessIntent.PRODUCT_QUERY:
        if "product_id" in missing_slots:
            return "请问您想了解哪款商品？可以告诉我商品名称或编号～"

    elif intent == BusinessIntent.SIZE_RECOMMEND:
        if "product_id" in missing_slots:
            return "请问您需要推荐哪款商品的尺码？请提供商品编号或名称～"
        elif "height" in missing_slots or "weight" in missing_slots:
            return "请告诉我您的身高和体重，我来为您推荐合适的尺码～"

    elif intent == BusinessIntent.LOGISTICS_QUERY:
        if "order_id" in missing_slots:
            return "请问您要查询哪个订单的物流信息？请提供订单号～"

    elif intent == BusinessIntent.RETURN:
        if "order_id" in missing_slots:
            return "请问您要退货的订单号是多少？"

    elif intent == BusinessIntent.EXCHANGE:
        if "order_id" in missing_slots:
            return "请问您要换货的订单号是多少？"

    elif intent == BusinessIntent.URGE_SHIPPING:
        if "order_id" in missing_slots:
            return "请问您要催发货的订单号是多少？"

    # 通用补槽提示（仅当上面没有匹配时使用）
    slot_names = {
        "product_id": "商品编号",
        "product_name": "商品名称",
        "order_id": "订单号",
        "promotion_type": "优惠类型",
        "height": "身高",
        "weight": "体重",
    }

    missing_names = [slot_names.get(slot, slot) for slot in missing_slots]
    return f"请提供以下信息：{', '.join(missing_names)}～"


def _generate_product_response_from_flow(
    flow_result: FlowResult,
    message: str,
    turn_id: str,
) -> str:
    """
    P1-07 修复：从 FlowResult 生成商品查询响应

    FlowResult.objects 包含商品列表
    """
    logger.info(f"[{turn_id}] 生成商品查询响应")

    products = flow_result.objects

    if not products:
        return "抱歉，暂时没有找到符合条件的商品。您可以试试其他关键词，或者告诉我更具体的需求～"

    # 构建商品列表响应
    total = len(products)

    # 从 tool_result.data 获取额外信息
    retrieval_mode = flow_result.tool_result.data.get("retrieval_mode", "rag")

    if retrieval_mode == "direct" and total == 1:
        # 精确查询：单个商品详情
        product = products[0]
        product_name = product.get("product_display_name", "商品")
        brand = product.get("brand", "")
        response_parts = [f"为您找到了 {brand} {product_name}：\n"]
    else:
        # RAG 查询：多个商品推荐
        response_parts = [f"为您找到了 {total} 款商品，这里是前几款推荐：\n"]

    # 展示前3个商品
    for i, product in enumerate(products[:3], 1):
        product_name = product.get("title") or product.get("product_display_name", "商品")
        brand = product.get("brand", "")

        # P1-32: 使用 ProductCard 格式字段
        selected_sku_price = product.get("selected_sku_price")
        matched_skus = product.get("matched_skus", [])

        product_line = f"{i}. {brand} {product_name}"

        if selected_sku_price:
            product_line += f" - ¥{selected_sku_price}"

        # 从 matched_skus 中提取颜色和库存信息
        if matched_skus:
            first_sku = matched_skus[0]
            color = first_sku.get("color", "")
            stock_status = first_sku.get("stock_status", "")

            if color:
                product_line += f" ({color})"
            if stock_status == "有货":
                product_line += " ✓ 有货"

        response_parts.append(product_line)

    if total > 3:
        response_parts.append(f"\n还有更多商品可供选择～")

    response_parts.append("\n您可以告诉我商品编号，我可以为您提供更详细的信息哦～")

    return "\n".join(response_parts)


def _generate_promotion_response_from_flow(
    flow_result: FlowResult,
    message: str,
    turn_id: str,
) -> str:
    """
    P1-07 修复：从 FlowResult 生成促销查询响应

    FlowResult.objects 包含促销列表
    """
    logger.info(f"[{turn_id}] 生成促销查询响应")

    promotions = flow_result.objects
    product_name = flow_result.tool_result.data.get("product_name", "该商品")

    if not promotions:
        return f"我查到了 {product_name}，当前没有适用的促销活动。请关注我们的活动页面，有新活动会第一时间通知您～"

    # 构建促销列表响应
    response_parts = [f"{product_name} 有以下优惠活动：\n"]

    # 展示所有促销（通常一个商品促销不会太多）
    for i, item in enumerate(promotions, 1):
        promo_name = item.get("promotion_name", "优惠活动")
        promo_type = item.get("promotion_type", "")
        description = item.get("description", "")

        promo_line = f"{i}. {promo_name}"

        # 根据真实的 promotion_type 和字段格式化
        if promo_type == "PERCENTAGE_DISCOUNT":
            discount_rate = item.get("discount_rate")
            if discount_rate:
                # discount_rate=0.9 表示九折
                discount_percent = int(discount_rate * 10)
                promo_line += f" - {discount_percent}折"
        elif promo_type == "FIXED_DISCOUNT":
            discount_amount = item.get("discount_amount")
            if discount_amount:
                promo_line += f" - 立减¥{discount_amount}"
        elif promo_type == "PROMO_PRICE":
            promo_price = item.get("promo_price")
            if promo_price:
                promo_line += f" - 促销价¥{promo_price}"

        if description:
            promo_line += f" ({description})"

        response_parts.append(promo_line)

    response_parts.append("\n快来选购吧！有任何问题随时问我～")

    return "\n".join(response_parts)


async def _generate_conversion_response_from_flow(
    flow_result: FlowResult,
    message: str,
    turn_id: str,
) -> str:
    """
    P0-28, P0-29 修复：使用 LLM + Jinja2 模板生成催拍催付响应

    修复内容：
    1. 使用 urge_order_payment.jinja2 模板
    2. 调用 LLM 生成个性化话术
    3. 传递 ConversionEvidence 真实数据到模板
    4. 移除无证据营销断言（如"品质值得信赖"、"现在入手更划算"）
    5. 修正库存逻辑：has_stock=False 显示"当前无可售库存"而不是"库存紧张"

    FlowResult.tool_result.data 包含 ConversionEvidence
    """
    logger.info(f"[{turn_id}] 使用 LLM 生成催拍催付响应")

    evidence = flow_result.tool_result.data.get("evidence", {})

    if not evidence:
        logger.warning(f"[{turn_id}] 无证据数据，返回 fallback 响应")
        return "我理解您的顾虑。有什么具体问题我可以帮您解答吗？"

    # 提取证据数据
    product_id = evidence.get("product_id")
    product_name = evidence.get("product_name")
    selling_points = evidence.get("product_selling_points", [])
    hesitation_signals = evidence.get("hesitation_signals", [])
    promotions = evidence.get("current_promotions", [])
    user_needs = evidence.get("user_need", [])
    verified_material = evidence.get("verified_material")
    stock_summary = evidence.get("verified_stock_summary")

    # 判断紧急程度
    urgency_level = "low"
    if hesitation_signals:
        # 如果有多个犹豫信号或包含价格/对比，提升紧急度
        if len(hesitation_signals) >= 2 or "price_concern" in hesitation_signals or "comparison" in hesitation_signals:
            urgency_level = "medium"
        # 如果库存紧张或促销即将结束，提升到高紧急度
        if stock_summary and stock_summary.get("has_stock") and stock_summary.get("total_quantity", 0) < 10:
            urgency_level = "high"
        if promotions and any(promo.get("end_time") for promo in promotions):
            urgency_level = "high"

    # 渲染模板
    try:
        prompt = render_prompt(
            "response/urge_order_payment.jinja2",
            conversion_type="purchase_decision",
            urgency_level=urgency_level,
            focused_product_id=product_id,
            product_name=product_name,
            user_query=message,
            # 传递真实证据
            selling_points=selling_points,
            promotions=promotions,
            verified_material=verified_material,
            stock_summary=stock_summary,
            hesitation_signals=hesitation_signals,
            user_needs=user_needs,
        )

        logger.debug(f"[{turn_id}] 渲染后的 prompt 长度: {len(prompt)} 字符")

        # 调用 LLM 生成响应
        llm = get_llm()
        response = await llm.ainvoke(prompt)
        generated_text = response.content.strip()

        logger.info(f"[{turn_id}] LLM 生成响应成功，长度: {len(generated_text)} 字符")

        # Grounding 验证：检查生成内容是否基于证据
        # 简单验证：如果生成内容包含无证据断言，记录警告
        ungrounded_phrases = ["品质值得信赖", "性价比高", "物超所值", "现在入手更划算"]
        for phrase in ungrounded_phrases:
            if phrase in generated_text:
                logger.warning(f"[{turn_id}] 检测到可能的无证据断言: {phrase}")

        return generated_text

    except Exception as e:
        logger.error(f"[{turn_id}] LLM 生成响应失败: {e}")
        # Fallback：返回基于证据的简单响应
        fallback_parts = []
        if product_name:
            fallback_parts.append(f"关于{product_name}，")
        if selling_points:
            fallback_parts.append(f"它具有{selling_points[0]}等特点。")
        if promotions:
            fallback_parts.append(f"目前有{promotions[0].get('promotion_name', '优惠活动')}。")
        fallback_parts.append("如果您还有疑问，请随时告诉我～")
        return "".join(fallback_parts) if fallback_parts else "有什么我可以帮您的吗？"


def _generate_chitchat_response(message: str) -> str:
    """生成闲聊响应"""
    message_lower = message.lower()

    # 简单的规则响应
    if any(word in message_lower for word in ["你好", "您好", "hi", "hello"]):
        return "您好！我是探域电商售前助手，很高兴为您服务～有什么可以帮您的吗？"
    elif any(word in message_lower for word in ["谢谢", "感谢", "多谢", "thanks", "thank"]):
        return "不客气！很高兴能帮到您～还有其他问题吗？"
    elif any(word in message_lower for word in ["再见", "拜拜", "bye"]):
        return "再见！祝您购物愉快，有需要随时找我哦～"
    else:
        return f"收到您的消息。我是探域电商售前助手，可以帮您查询商品信息、促销活动等。有什么需要帮助的吗？"


def _generate_resume_task_prompt(state: AgentState, task_transition) -> str:
    """
    问题6修复: 生成任务恢复提示

    当完成或取消任务后恢复旧任务时，生成明确的提示
    """
    active_task = state.get("active_task")

    if not active_task:
        return "好的，已处理完毕。还有什么我可以帮您的吗？"

    # 根据任务转移类型生成不同的提示
    action = task_transition.action if task_transition else "unknown"
    intent = active_task.intent

    # 意图到中文名称的映射
    intent_name_map = {
        BusinessIntent.PRODUCT_QUERY: "商品咨询",
        BusinessIntent.PROMOTION_QUERY: "促销查询",
        BusinessIntent.LOGISTICS_QUERY: "物流查询",
        BusinessIntent.RETURN: "退货申请",
        BusinessIntent.EXCHANGE: "换货申请",
        BusinessIntent.URGE_ORDER_PAYMENT: "催拍催付",
        BusinessIntent.URGE_SHIPPING: "催发货",
        BusinessIntent.SIZE_RECOMMEND: "尺码推荐",
        BusinessIntent.CHITCHAT: "闲聊",
    }

    intent_name = intent_name_map.get(intent, "之前的任务")

    if action == "cancel":
        return f"好的，已为您取消当前操作。之前的{intent_name}可以继续，请问您想继续吗？"
    elif action == "complete":
        return f"好的，已完成。之前的{intent_name}可以继续，请问您还需要什么帮助吗？"
    else:
        return f"好的，我们回到之前的{intent_name}。请问您需要什么帮助？"

