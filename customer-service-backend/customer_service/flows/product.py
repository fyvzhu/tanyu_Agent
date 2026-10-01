"""
商品查询 Flow - 处理商品检索和详情查询

P0-02 修复：
- 不再自建 ProductRetrievalService
- Discovery 路径通过 ToolRuntime 调用 product_search_tool
- 保持独立的 RAG 模块，统一业务入口

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
from customer_service.retrieval.context_resolver import ContextResolver
from customer_service.flows.models import FlowResult
from customer_service.retrieval.query_planner import QueryPlanner
from customer_service.tools.registry import get_global_tool_runtime
from customer_service.tools.context import ToolExecutionContext
from customer_service.intents.models import BusinessIntent


class ProductQueryFlow:
    """
    商品查询 Flow

    职责（P0-02 修复后）：
    1. 解析用户查询中的商品指代和约束条件
    2. 规划查询路径（direct/rag/clarify）
    3. Exact: 直接调用 Commerce API
    4. Discovery: 通过 ToolRuntime 调用 product_search_tool（统一 RAG 入口）
    5. Clarify: 返回澄清提示
    """

    intent_name = "product_query"

    def __init__(self):
        self.context_resolver = ContextResolver()
        self.query_planner = QueryPlanner()
        self.commerce = get_ecommerce_client()
        self.tool_runtime = get_global_tool_runtime()

        logger.info(f"✅ ProductQueryFlow 初始化（通过 ToolRuntime 统一调用 RAG）")
    
    async def execute(self, state: AgentState, runtime: AgentRuntimeContext) -> FlowResult:
        """
        执行商品查询

        P1-07 修复：返回统一的 FlowResult 契约
        P0 修复：从 runtime 获取 session_id, user_id, user_access_token

        Args:
            state: Agent 状态（不包含 user_id/session_id/token）
            runtime: Runtime Context（包含 session_id, user_id, user_access_token）

        Returns:
            FlowResult: 统一的 Flow 执行结果
            - ready_for_response: True 表示可以生成响应，False 表示需要澄清
            - tool_result: 工具执行结果（包含商品数据）
            - dialogue_reason: "clarify" | "error" | None
            - objects: 商品列表
        """
        user_query = state.get("current_message", "")
        session_id = runtime.session_id

        logger.info(f"[{session_id}] 🔍 ProductQueryFlow: {user_query}")

        try:
            # 1. 解析上下文
            context = await self.context_resolver.resolve(user_query, state)
            logger.debug(f"[{session_id}] Context resolved: focused_product={context.focused_product_id}")

            # 2. 规划查询路径
            plan = self.query_planner.plan(context)
            logger.info(f"[{session_id}] Query plan: {plan}")

            # 3. 根据路径执行
            if plan == "direct":
                return await self._execute_direct_query(context, runtime)
            elif plan == "rag":
                return await self._execute_rag_query(context, runtime, state)
            else:  # clarify
                return await self._execute_clarify(context, runtime)

        except Exception as e:
            logger.error(f"[{runtime.session_id}] ❌ ProductQueryFlow error: {e}", exc_info=True)
            from customer_service.tools.models import ToolResult, ToolError
            return FlowResult(
                ready_for_response=True,
                tool_result=ToolResult(
                    tool_name="product_query_flow",  # P0-27: 添加必填字段 tool_name
                    ok=False,
                    error=ToolError(code="FLOW_ERROR", message=str(e), retryable=False),
                    data={}
                ),
                dialogue_reason="error",
                objects=[]
            )

    async def _execute_direct_query(
        self,
        context: Any,
        runtime: AgentRuntimeContext
    ) -> FlowResult:
        """执行直接查询（有明确 product_id）

        P1-07 修复：返回 FlowResult
        P0 修复：从 runtime 获取 session_id
        P1-32/P1-33 修复：返回 ProductCard 格式的 objects
        """
        from customer_service.tools.models import ToolResult

        session_id = runtime.session_id

        # 优先使用 explicit_product_id，其次使用 focused_product_id
        target_product_id = context.explicit_product_id or context.focused_product_id

        if not target_product_id:
            logger.error(f"[{session_id}] ❌ Direct query without product_id")
            from customer_service.tools.models import ToolError
            return FlowResult(
                ready_for_response=False,
                tool_result=ToolResult(
                    tool_name="product_query_flow",  # P0-27: 添加必填字段 tool_name
                    ok=False,
                    error=ToolError(code="NO_PRODUCT_ID", message="No product_id available", retryable=False),
                    data={}
                ),
                dialogue_reason="clarify",
                objects=[]
            )

        logger.info(f"[{session_id}] 🎯 Direct query for product: {target_product_id}")

        # 获取商品详情
        product = await self.commerce.get_product(target_product_id)

        # 获取 SKU 信息
        skus = await self.commerce.get_skus(target_product_id)

        # P1-32: 转换为 ProductCard 格式
        product_cards = []
        if product:
            product_cards = [self._to_product_card(product, skus)]

        return FlowResult(
            ready_for_response=True,
            tool_result=ToolResult(
                tool_name="product_query_flow",  # P0-27: 添加必填字段 tool_name
                ok=True,
                data={
                    "products": [product] if product else [],
                    "skus": skus,
                    "retrieval_mode": "direct"
                }
            ),
            dialogue_reason=None,
            objects=product_cards
        )
    
    async def _execute_rag_query(
        self,
        context: Any,
        runtime: AgentRuntimeContext,
        state: AgentState
    ) -> FlowResult:
        """
        执行 RAG 检索（语义搜索）

        任务一修复：真正通过 ToolRuntime 统一入口调用 product_search_tool
        不再使用"临时方案"直接获取 handler

        P1-07 修复：返回 FlowResult
        P0 修复：从 runtime 参数获取 session_id, user_id, user_access_token
        """
        from customer_service.tools.models import ToolResult, ToolError

        session_id = runtime.session_id
        logger.info(f"[{session_id}] 🔍 RAG query via ToolRuntime: '{context.semantic_query}'")

        # 构造 product_search_tool 参数
        # P1-05 修复：传递完整的硬约束链（brand, category, color, size, price）
        tool_args = {
            "query": context.semantic_query,
            "brand": context.hard_filters.get("brand"),
            "category": context.hard_filters.get("category"),
            "color": context.hard_filters.get("color"),
            "size": context.hard_filters.get("size"),
            "min_price": context.hard_filters.get("min_price"),
            "max_price": context.hard_filters.get("max_price"),
            "in_stock_only": True,
            "top_k": 5,
        }

        # 任务一修复：直接使用传入的 runtime context
        tool_context = ToolExecutionContext(
            runtime=runtime,
            intent=BusinessIntent.PRODUCT_QUERY,
        )

        # 任务一修复：通过 ToolRuntime.execute() 统一入口调用
        # 不再直接调用 handler
        try:
            tool_result = await self.tool_runtime.execute(
                name="product_search_tool",
                args=tool_args,
                context=tool_context,
            )
        except Exception as e:
            logger.error(f"[{session_id}] ❌ ToolRuntime.execute failed: {e}", exc_info=True)
            return FlowResult(
                ready_for_response=True,
                tool_result=ToolResult(
                    tool_name="product_query_flow",  # P0-27: 添加必填字段 tool_name
                    ok=False,
                    error=ToolError(code="TOOL_ERROR", message=str(e), retryable=False),
                    data={}
                ),
                dialogue_reason="error",
                objects=[]
            )

        if not tool_result.ok:
            logger.error(f"[{session_id}] ❌ product_search_tool failed: {tool_result.error}")
            return FlowResult(
                ready_for_response=True,
                tool_result=tool_result,
                dialogue_reason="error",
                objects=[]
            )

        # 提取 Tool 返回的数据
        data = tool_result.data or {}
        candidates = data.get("candidates", [])
        retrieval_mode = data.get("retrieval_mode", "unknown")

        logger.info(f"[{session_id}] ✅ product_search_tool returned {len(candidates)} candidates, mode={retrieval_mode}")

        # P1-32: 转换为 ProductCard 格式
        # P7 修复: 正确处理 Commerce-only 降级路径（无 selected_sku）
        product_cards = []
        for candidate in candidates:
            product_id = candidate.get("product_id")
            if not product_id:
                continue

            # 从 candidate 提取 selected_sku
            selected_sku = candidate.get("selected_sku")

            # P7 修复: Commerce-only 路径使用 min_price/max_price 而非 selected_sku.price
            if selected_sku:
                # RAG 路径: 有具体 SKU
                min_price = selected_sku.get("price")
                max_price = selected_sku.get("price")
                matched_skus = [selected_sku]
                selected_sku_id = selected_sku.get("sku_id")
                selected_sku_price = selected_sku.get("price")
            else:
                # Commerce-only 降级路径: 无具体 SKU，使用价格范围
                min_price = candidate.get("min_price")
                max_price = candidate.get("max_price")
                matched_skus = []
                selected_sku_id = None
                selected_sku_price = None

            # 构造 ProductCard
            # 问题修复2: 确保字段与 ProductCard 模型完全匹配
            product_card = {
                "type": "product_card",
                "product_id": product_id,
                "title": candidate.get("product_display_name"),
                "brand": candidate.get("brand"),
                "main_image_url": candidate.get("main_image_url"),  # P7: 两条路径都有此字段
                "min_price": float(min_price) if min_price is not None else None,
                "max_price": float(max_price) if max_price is not None else None,
                "selected_sku_id": selected_sku_id,
                "selected_sku_price": float(selected_sku_price) if selected_sku_price is not None else None,
                "stock_status": matched_skus[0].get("stock_status") if matched_skus else None,
            }
            product_cards.append(product_card)

        return FlowResult(
            ready_for_response=True,
            tool_result=tool_result,
            dialogue_reason=None,
            objects=product_cards
        )
    
    async def _execute_clarify(
        self,
        context: Any,
        runtime: AgentRuntimeContext
    ) -> FlowResult:
        """需要澄清（指代不明确）

        P1-07 修复：返回 FlowResult
        P0 修复：从 runtime 获取 session_id
        """
        from customer_service.tools.models import ToolResult

        logger.info(f"[{runtime.session_id}] ❓ Clarification needed")

        return FlowResult(
            ready_for_response=False,
            tool_result=ToolResult(
                tool_name="product_query_flow",  # P0-27: 添加必填字段 tool_name
                ok=True,
                data={
                    "retrieval_mode": "clarify",
                    "conversation_products": context.conversation_products
                }
            ),
            dialogue_reason="clarify",
            objects=[]
        )

    def _to_product_card(self, product: dict[str, Any], skus: list[dict[str, Any]]) -> dict[str, Any]:
        """
        将原始商品数据转换为 ProductCard 格式

        P1-32 修复：确保返回符合 07 Contract 的 ProductCard 格式
        问题7修复：使用 product["main_image_url"] 而不是 SKU 的 image_url

        Args:
            product: 商品详情（来自 Commerce API）
            skus: SKU 列表

        Returns:
            ProductCard 格式的字典
        """
        # 计算价格范围
        prices = [sku.get("price", 0) for sku in skus if sku.get("price")]
        min_price = min(prices) if prices else None
        max_price = max(prices) if prices else None

        # 选择默认 SKU（优先选择有货的）
        selected_sku = None
        for sku in skus:
            if sku.get("stock_status") == "in_stock":
                selected_sku = sku
                break

        # 如果没有有货 SKU，使用第一个
        if not selected_sku and skus:
            selected_sku = skus[0]

        # 构造 ProductCard（使用商品的 main_image_url）
        # 问题修复2: 确保字段与 ProductCard 模型完全匹配
        return {
            "type": "product_card",
            "product_id": product.get("product_id"),
            "title": product.get("product_display_name") or product.get("name"),
            "brand": product.get("brand"),
            "main_image_url": product.get("main_image_url"),  # 从商品详情获取
            "min_price": float(min_price) if min_price is not None else None,
            "max_price": float(max_price) if max_price is not None else None,
            "selected_sku_id": selected_sku.get("sku_id") if selected_sku else None,
            "selected_sku_price": float(selected_sku.get("price")) if selected_sku and selected_sku.get("price") else None,
            "stock_status": selected_sku.get("stock_status") if selected_sku else None,
        }
