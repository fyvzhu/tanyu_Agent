"""
LangGraph 节点 - Hallucination Guard
根据 01_slice_foundation 文档 #13 定义

核心职责：
- 检查生成的响应是否与 Evidence 对齐
- 检测幻觉（Hallucination）
- 必要时重新生成或使用 fallback

P0 架构修复：
- 接受 config 参数以符合 LangGraph 规范
- 当前不使用 runtime context，但保持签名一致性
"""
from __future__ import annotations
import re
from typing import Any

from loguru import logger
from langgraph.types import RunnableConfig

from customer_service.graph.state import AgentState
from customer_service.intents.models import BusinessIntent, GuardStatus  # 阶段1修复：导入GuardStatus


def extract_factual_claims(response: str) -> list[str]:
    """
    从响应中提取事实性陈述

    简化版：提取包含数字、价格、品牌等的陈述
    实际应该使用 NER 或 LLM 提取
    """
    claims = []

    # 提取价格陈述（如：¥199、199元）- 不包括单独的数字
    price_matches = re.findall(r'[¥￥]\s*\d+(?:\.\d+)?|\d+(?:\.\d+)?\s*元', response)
    claims.extend([f"price:{match}" for match in price_matches])

    # 提取数量陈述（如：5款商品、3个活动）- 必须有量词
    quantity_matches = re.findall(r'(\d+)\s*(款|个|件|条|项)', response)
    claims.extend([f"quantity:{num}{unit}" for num, unit in quantity_matches])

    # 提取折扣陈述（如：8折、80折）
    discount_matches = re.findall(r'\d+\s*折', response)
    claims.extend([f"discount:{match}" for match in discount_matches])

    # 提取品牌陈述（常见英文品牌名）
    # 先尝试常见品牌名精确匹配
    common_brands = ['Nike', 'Adidas', 'Puma', 'Reebok', 'New Balance', 'Under Armour', 'Converse', 'Vans', 'Fila']
    for brand in common_brands:
        if brand in response:
            claims.append(f"brand:{brand}")

    # 再尝试提取其他大写开头的英文词
    other_brands = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\b', response)
    for match in other_brands:
        if len(match) > 2 and match not in common_brands and match not in ['For', 'The', 'And', 'Or', 'From', 'With']:
            claims.append(f"brand:{match}")

    return claims


def verify_claim_against_evidence(claim: str, flow_result: Any) -> bool:
    """
    P1-47 修复：从新 FlowResult 契约提取证据

    验证陈述是否有 Evidence 支持

    证据来源：
    1. FlowResult.tool_result.evidence (EvidenceItem[])
    2. FlowResult.tool_result.data (结构化数据)
    3. FlowResult.objects (ProductCard 等)

    Args:
        claim: 事实性陈述（如 "price:¥199"）
        flow_result: FlowResult 对象

    Returns:
        True 如果有证据支持，False 如果没有
    """
    if not flow_result:
        return False

    # P1-47: 从新契约提取证据
    from customer_service.flows.models import FlowResult

    products = []
    evidence_items = []
    structured_data = {}

    if isinstance(flow_result, FlowResult):
        # 1. 从 objects 提取（ProductCard 等）
        products = flow_result.objects or []

        # 2. 从 tool_result 提取
        if flow_result.tool_result:
            # 提取 evidence
            evidence_items = flow_result.tool_result.evidence or []
            # 提取 data
            structured_data = flow_result.tool_result.data or {}

            # 从 data 中提取商品列表（兼容性）
            if "items" in structured_data and not products:
                products = structured_data.get("items", [])
            if "products" in structured_data and not products:
                products = structured_data.get("products", [])

    elif isinstance(flow_result, dict):
        # 兼容旧格式
        products = flow_result.get("products", [])
        if not products:
            data = flow_result.get("data", {})
            products = data.get("items", [])
            structured_data = data

    # 如果没有任何证据，无法验证
    if not products and not evidence_items and not structured_data:
        return False

    # 提取陈述类型和值
    if ":" not in claim:
        return True  # 无法分类的陈述，保守地认为有效

    claim_type, claim_value = claim.split(":", 1)
    claim_value_clean = re.sub(r'[¥￥元\s]', '', claim_value)

    # 根据类型验证
    if claim_type == "price":
        # 检查价格是否在商品数据中
        for product in products:
            if "default_sku" in product:
                sku_price = str(product["default_sku"].get("price", ""))
                if claim_value_clean in sku_price:
                    return True
            if "discount_value" in product:
                discount = str(product.get("discount_value", ""))
                if claim_value_clean in discount:
                    return True

    elif claim_type == "quantity":
        # 检查数量是否匹配
        quantity_match = re.search(r'\d+', claim_value)
        if quantity_match:
            claimed_quantity = int(quantity_match.group())
            actual_count = len(products)
            # 允许一些误差（如"找到5款"实际可能是4-6款）
            if abs(claimed_quantity - actual_count) <= 1:
                return True

    elif claim_type == "brand":
        # 检查品牌是否在商品数据中
        for product in products:
            brand = product.get("brand", "")
            # 支持部分匹配（如 "Levis" 匹配 "Levi's"）
            if claim_value.lower() in brand.lower() or brand.lower() in claim_value.lower():
                return True

    elif claim_type == "discount":
        # 检查折扣是否匹配
        for product in products:
            if "discount_value" in product:
                discount_value = product.get("discount_value", 0)
                if "promotion_type" in product and product["promotion_type"] == "percentage_discount":
                    # 百分比折扣
                    discount_percent = int(discount_value * 100)
                    if str(discount_percent) in claim_value:
                        return True

    # P1-47: 在 evidence_items 中验证
    for evidence in evidence_items:
        if hasattr(evidence, "facts") and evidence.facts:
            # 检查 facts 字典中是否有相关证据
            if claim_type.lower() in evidence.facts:
                return True

    # P1-47: 在 structured_data 中验证
    if claim_type.lower() in structured_data:
        return True

    # 默认：无法验证
    return False


def calculate_hallucination_score(
    response: str,
    flow_result: Any,
    intent: BusinessIntent
) -> tuple[float, list[str]]:
    """
    计算幻觉分数

    Args:
        response: 生成的响应文本
        flow_result: FlowResult 对象
        intent: 业务意图

    Returns:
        (score, unsupported_claims)
        - score: 0.0-1.0，越高越可能是幻觉
        - unsupported_claims: 没有证据支持的陈述列表
    """
    # CHITCHAT 不需要 Evidence，直接返回0
    if intent == BusinessIntent.CHITCHAT:
        return 0.0, []

    # 提取事实性陈述
    claims = extract_factual_claims(response)

    if not claims:
        # 没有可验证的陈述，可能是纯文本引导，认为安全
        return 0.0, []

    # 验证每个陈述
    unsupported = []
    for claim in claims:
        if not verify_claim_against_evidence(claim, flow_result):
            unsupported.append(claim)

    # 计算分数：无证据支持的陈述比例
    score = len(unsupported) / len(claims) if claims else 0.0

    return score, unsupported


async def hallucination_guard_node(state: AgentState, config: RunnableConfig) -> AgentState:
    """
    节点 5: Hallucination Guard

    逻辑：
    1. 检查 response_draft 是否基于 Evidence
    2. 检测是否有幻觉内容
    3. 如果检测到幻觉，标记并使用 fallback
    """
    turn_id = state.get("turn_id", "unknown")
    response_draft = state.get("response_draft", "")
    flow_result = state.get("flow_result")
    active_task = state.get("active_task")
    guard_retry_count = state.get("guard_retry_count", 0)

    logger.info(f"[{turn_id}] === 节点 5: Hallucination Guard 开始 ===")

    # P0修复：提前return的分支必须设置guard_status
    # 参考修改建议1第五、六节

    if not response_draft:
        logger.error(f"[{turn_id}] ❌ response_draft 缺失，这是内部异常")

        state["response_draft"] = "抱歉，当前请求处理出现异常，请稍后重试～"
        state["fallback_used"] = True
        state["hallucination_detected"] = False
        state["hallucination_score"] = 0.0
        state["guard_status"] = GuardStatus.FALLBACK

        return state

    if not active_task:
        # P0修复：无active_task表示这是CHITCHAT/CLARIFY/CANCEL等非业务事实响应
        # 这些响应没有需要验证的业务数据，直接PASS
        logger.info(
            f"[{turn_id}] ℹ️ 无 active_task，"
            "视为非业务事实响应（CHITCHAT/CLARIFY/CANCEL等），Guard 直接通过"
        )

        state["hallucination_detected"] = False
        state["hallucination_score"] = 0.0
        state["guard_status"] = GuardStatus.PASS

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

    # 计算幻觉分数
    hallucination_score, unsupported_claims = calculate_hallucination_score(
        response_draft, flow_result, intent
    )

    # 阈值：超过 30% 的陈述无证据支持，认为可能有幻觉
    HALLUCINATION_THRESHOLD = 0.3

    if hallucination_score > HALLUCINATION_THRESHOLD:
        logger.warning(
            f"[{turn_id}] ⚠️ 检测到可能的幻觉 "
            f"(score={hallucination_score:.2f}, unsupported={len(unsupported_claims)})"
        )
        logger.debug(f"[{turn_id}] 无证据支持的陈述: {unsupported_claims}")

        # 使用 fallback 回复
        if intent == BusinessIntent.PRODUCT_QUERY:
            fallback_response = "抱歉，我暂时无法准确回答您的问题。建议您浏览商品页面或联系客服获取准确信息～"
        elif intent == BusinessIntent.PROMOTION_QUERY:
            fallback_response = "抱歉，我暂时无法准确回答关于促销活动的问题。建议您访问活动页面或联系客服了解详情～"
        else:
            fallback_response = "抱歉，我暂时无法准确回答您的问题。请联系客服获取帮助～"

        state["response_draft"] = fallback_response
        state["fallback_used"] = True
        # 阶段1修复：统一使用GuardStatus枚举
        state["hallucination_detected"] = True
        state["guard_status"] = GuardStatus.FALLBACK  # 修复：使用统一的枚举值
        state["hallucination_score"] = hallucination_score

        logger.info(f"[{turn_id}] 🔄 使用 fallback 回复")
    else:
        logger.info(
            f"[{turn_id}] ✅ Hallucination Guard 通过 "
            f"(score={hallucination_score:.2f}, retry_count={guard_retry_count})"
        )
        # 阶段1修复：统一使用GuardStatus枚举
        state["hallucination_detected"] = False
        state["guard_status"] = GuardStatus.PASS  # 修复：使用统一的枚举值
        state["hallucination_score"] = hallucination_score

    logger.info(f"[{turn_id}] === 节点 5: Hallucination Guard 完成 ===")

    # 阶段3修复：Guard 检查后，判断是否完成任务
    # 根据文档第52行："在确认本轮成功且回复不会被 Guard 拒绝后，才调用 complete_current()"
    if should_complete_task(state):
        from customer_service.graph.task_context_manager import TaskContextManager
        logger.info(f"[{turn_id}] 🎯 本轮任务成功且 Guard 通过，完成当前任务并恢复暂停任务")
        state = TaskContextManager.complete_current(state, turn_id)
    else:
        logger.info(f"[{turn_id}] ⏸️ 本轮未完成任务（等待补槽、错误或 Guard 拦截）")

    return state


def should_complete_task(state: AgentState) -> bool:
    """
    阶段3修复：判断是否应该完成当前任务

    根据文档第52行："在确认本轮成功且回复不会被 Guard 拒绝后，才调用 complete_current()"

    完成条件：
    1. Guard 状态为 PASS（不是 FALLBACK 或 RETRY）
    2. FlowResult 状态为 SUCCESS
    3. tool_result.ok = True
    4. ready_for_response = True

    不完成的情况：
    - WAITING_SLOT: 等待补槽
    - CLARIFY: 需要澄清
    - Tool 错误: 失败或可重试
    - Guard 拦截: FALLBACK 或 RETRY

    Args:
        state: Agent状态

    Returns:
        是否应该完成任务
    """
    from customer_service.intents.models import GuardStatus
    from customer_service.flows.models import FlowStatus

    guard_status = state.get("guard_status")
    flow_result = state.get("flow_result")

    # Guard 未通过，不完成任务
    if guard_status != GuardStatus.PASS:
        return False

    # 没有 flow_result，不完成
    if not flow_result:
        return False

    # FlowResult 状态不是 SUCCESS，不完成
    if flow_result.status and flow_result.status != FlowStatus.SUCCESS:
        return False

    # 未准备好响应，不完成
    if not flow_result.ready_for_response:
        return False

    # tool_result 失败，不完成
    if flow_result.tool_result and not flow_result.tool_result.ok:
        return False

    # 所有条件满足，可以完成
    return True
