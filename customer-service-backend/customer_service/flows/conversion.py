"""
催拍催付 Flow - 基于真实证据的个性化转化

P0-07/P1-01 修复：
- 不要求 order_id（这是对话转化，不是订单操作）
- 聚合真实的 ConversionEvidence（商品卖点、促销、用户需求）
- 为 response_gen 提供完整证据，而非仅元数据

P1-07 修复：
- 返回统一的 FlowResult 契约
- ready_for_response, tool_result, dialogue_reason, objects

P0 架构修复：
- execute() 接收 runtime context 参数
- 从 runtime 获取 session_id, user_id, user_access_token
"""
from __future__ import annotations

from typing import Any

from loguru import logger

from customer_service.graph.state import AgentState
from customer_service.context.runtime import AgentRuntimeContext
from customer_service.clients.ecommerce import get_ecommerce_client
from customer_service.flows.models import FlowResult, ConversionEvidence


class UrgeOrderPaymentFlow:
    """
    催拍催付 Flow（转化对话）

    职责（P0-07 修复后）：
    1. 识别用户犹豫点（价格、质量、对比、时机）
    2. 聚合真实商品证据：卖点、材质、当前促销
    3. 提供 ConversionEvidence 供 response_gen 生成个性化话术

    重要区别：
    - urge_order_payment = Agent 促进用户下单/付款（转化对话）
    - urge_shipping = 用户催促商家发货（订单操作，属 Slice04）
    """

    intent_name = "urge_order_payment"

    def __init__(self):
        self.commerce = get_ecommerce_client()

    async def execute(self, state: AgentState, runtime: AgentRuntimeContext) -> FlowResult:
        """
        执行转化证据聚合

        流程：
        1. 确定焦点商品（缺商品时返回澄清状态）
        2. 读取商品详情、Knowledge Card、卖点
        3. 查询当前适用促销
        4. 识别用户需求和犹豫点
        5. 返回完整 ConversionEvidence

        P1-07 修复：返回 FlowResult
        P0 修复：从 runtime 获取 session_id, user_id, user_access_token

        Args:
            state: Agent 状态
            runtime: Runtime Context

        Returns:
            FlowResult: 统一的 Flow 执行结果
        """
        from customer_service.tools.models import ToolResult, ToolError

        user_query = state.get("current_message", "")
        session_id = runtime.session_id

        logger.info(f"[{session_id}] 💰 UrgeOrderPaymentFlow (转化对话): {user_query}")

        try:
            # 1. 确定焦点商品
            product_id = self._get_focused_product(state)

            if not product_id:
                logger.info(f"[{session_id}] ⚠️ 缺少焦点商品，需要澄清")
                return FlowResult(
                    ready_for_response=False,
                    tool_result=ToolResult(
                        tool_name="conversion_flow",  # P0-27: 添加必填字段 tool_name
                        ok=True,
                        data={
                            "missing_slot": "product_id",
                            "clarification": "您是想了解哪款商品呢？可以告诉我商品名称或编号。"
                        }
                    ),
                    dialogue_reason="clarify",
                    objects=[]
                )

            logger.info(f"[{session_id}] ✅ 焦点商品: {product_id}")

            # 2. 聚合真实证据
            evidence = await self._gather_conversion_evidence(
                product_id=product_id,
                user_query=user_query,
                state=state,
                runtime=runtime,
            )

            return FlowResult(
                ready_for_response=True,
                tool_result=ToolResult(
                    tool_name="conversion_flow",  # P0-27: 添加必填字段 tool_name
                    ok=True,
                    data={
                        "evidence": evidence.model_dump(),  # P1-30: 转为 dict
                        "product_id": product_id
                    }
                ),
                dialogue_reason=None,
                objects=[{"product_id": product_id, "evidence": evidence.model_dump()}]  # P1-30: 转为 dict
            )

        except Exception as e:
            logger.error(f"[{session_id}] ❌ UrgeOrderPaymentFlow error: {e}", exc_info=True)
            return FlowResult(
                ready_for_response=True,
                tool_result=ToolResult(
                    tool_name="conversion_flow",  # P0-27: 添加必填字段 tool_name
                    ok=False,
                    error=ToolError(code="FLOW_ERROR", message=str(e), retryable=False),
                    data={}
                ),
                dialogue_reason="error",
                objects=[]
            )

    async def _gather_conversion_evidence(
        self,
        product_id: str,
        user_query: str,
        state: AgentState,
        runtime: AgentRuntimeContext,
    ) -> ConversionEvidence:
        """
        聚合真实的转化证据

        P0-07 修复：不是返回元数据，而是读取真实的商品、卖点、促销数据
        P0 修复：使用 runtime.session_id
        P1-30 修复：返回 ConversionEvidence Pydantic Model
        """
        session_id = runtime.session_id

        # P1-30: 使用 Pydantic Model
        evidence = ConversionEvidence(
            product_id=product_id,
            product_name=None,
            product_selling_points=[],
            verified_material=None,
            user_need=[],
            hesitation_signals=[],
            current_promotions=[],
            explicit_preferences={},
            relevant_memories=[],
            verified_stock_summary=None,
            evidence_sources=[],
        )

        # 1. 获取商品详情
        try:
            product = await self.commerce.get_product(product_id)
            if product:
                evidence.product_name = product.get("product_display_name") or product.get("name")
                evidence.verified_material = product.get("material")

                # 从商品数据提取卖点
                if "selling_points" in product:
                    evidence.product_selling_points = product["selling_points"]

                evidence.evidence_sources.append({
                    "type": "commerce_product",
                    "product_id": product_id,
                })

                logger.info(f"[{session_id}] ✅ 获取商品详情: {evidence.product_name}")
        except Exception as e:
            logger.error(f"[{session_id}] ⚠️ 获取商品详情失败: {e}")

        # 2. 获取当前适用促销
        # P0-31 修复：使用用户 JWT 调用促销 API，确保会员资格验证
        try:
            user_token = runtime.user_access_token.get_secret_value()
            promotions = await self.commerce.active_promotions(
                product_id=product_id,
                user_access_token=user_token
            )
            if promotions:
                evidence.current_promotions = promotions
                evidence.evidence_sources.append({
                    "type": "commerce_promotions",
                    "product_id": product_id,
                    "count": len(promotions),
                })
                logger.info(f"[{session_id}] ✅ 找到 {len(promotions)} 个适用促销")
        except Exception as e:
            logger.error(f"[{session_id}] ⚠️ 获取促销失败: {e}")

        # 3. 识别用户需求（从当前消息和历史提取）
        evidence.user_need = self._extract_user_needs(user_query, state)

        # 4. 识别犹豫信号
        evidence.hesitation_signals = self._detect_hesitation_signals(user_query)

        # 5. 获取库存摘要（如果可用）
        try:
            # 从商品详情中提取库存信息
            if product and "skus" in product:
                total_stock = sum(sku.get("stock", 0) for sku in product["skus"])
                evidence.verified_stock_summary = {
                    "total_stock": total_stock,
                    "has_stock": total_stock > 0,
                }
        except Exception as e:
            logger.error(f"[{session_id}] ⚠️ 提取库存摘要失败: {e}")

        logger.info(
            f"[{session_id}] 📊 ConversionEvidence: "
            f"selling_points={len(evidence.product_selling_points)}, "
            f"promotions={len(evidence.current_promotions)}, "
            f"hesitation={evidence.hesitation_signals}"
        )

        return evidence

    def _get_focused_product(self, state: AgentState) -> str | None:
        """
        获取焦点商品 ID

        P0-23 修复：从 v7 规范字段获取（统一使用 Pydantic 模型）
        """
        # 1. 优先从 active_task.slots 获取
        active_task = state.get("active_task")
        if active_task:
            slots = active_task.slots
            product_id = slots.get("product_id")
            if product_id:
                return product_id

        # 2. 从 conversation_focus 获取
        conversation_focus = state.get("conversation_focus")
        if conversation_focus:
            if conversation_focus.entity_type == "product":
                return conversation_focus.entity_id

        return None

    def _extract_user_needs(self, user_query: str, state: AgentState) -> list[str]:
        """从用户查询和历史中提取需求"""
        needs = []

        # 常见需求关键词
        need_patterns = {
            "舒适": ["舒适", "舒服", "透气"],
            "耐用": ["耐用", "质量好", "结实"],
            "时尚": ["好看", "时尚", "潮流", "设计"],
            "性价比": ["性价比", "实惠", "划算"],
            "通勤": ["通勤", "上班", "工作"],
            "运动": ["运动", "健身", "跑步"],
        }

        for need_type, keywords in need_patterns.items():
            if any(keyword in user_query for keyword in keywords):
                needs.append(need_type)

        return needs

    def _detect_hesitation_signals(self, user_query: str) -> list[str]:
        """检测犹豫信号"""
        signals = []

        hesitation_patterns = {
            "price_concern": ["贵", "便宜", "优惠", "打折", "降价"],
            "quality_doubt": ["质量", "好不好", "怎么样", "靠谱", "可靠"],
            "comparison": ["对比", "比较", "还有其他", "别的", "类似"],
            "timing": ["再等等", "过两天", "考虑", "想想", "犹豫"],
        }

        for signal_type, keywords in hesitation_patterns.items():
            if any(keyword in user_query for keyword in keywords):
                signals.append(signal_type)

        return signals


# 别名导出，方便导入
ConversionFlow = UrgeOrderPaymentFlow
