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
from typing import Any, TYPE_CHECKING

from loguru import logger

from customer_service.graph.state import AgentState
from customer_service.intents.models import BusinessIntent

if TYPE_CHECKING:
    from langgraph.types import RunnableConfig


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


async def hallucination_guard_node(state: AgentState, config: "RunnableConfig") -> AgentState:
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

    if not response_draft:
        logger.warning(f"[{turn_id}] ⚠️ 没有 response_draft，跳过检查")
        return state

    if not active_task:
        logger.warning(f"[{turn_id}] ⚠️ 没有 active_task，跳过检查")
        return state

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
        # P1-47: 统一状态字段，同时设置 hallucination_detected 和 guard_status
        state["hallucination_detected"] = True
        state["guard_status"] = "hallucination_detected"  # P1-47: 供路由读取
        state["hallucination_score"] = hallucination_score

        logger.info(f"[{turn_id}] 🔄 使用 fallback 回复")
    else:
        logger.info(
            f"[{turn_id}] ✅ Hallucination Guard 通过 "
            f"(score={hallucination_score:.2f}, retry_count={guard_retry_count})"
        )
        # P1-47: 统一状态字段
        state["hallucination_detected"] = False
        state["guard_status"] = "passed"  # P1-47: 供路由读取
        state["hallucination_score"] = hallucination_score

    logger.info(f"[{turn_id}] === 节点 5: Hallucination Guard 完成 ===")

    return state
