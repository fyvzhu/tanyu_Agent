"""
促销查询 Flow - 处理商品促销查询

P0-04 修复：
- 仅查询具体商品的促销活动
- 删除全站活动查询逻辑
- 缺唯一商品时返回 WAITING_SLOT 状态

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
from customer_service.tools.registry import get_global_tool_runtime
from customer_service.tools.context import ToolExecutionContext
from customer_service.intents.models import BusinessIntent
from customer_service.flows.models import FlowResult


class PromotionQueryFlow:
    """
    促销查询 Flow

    职责（P0-04 修复后）：
    1. 仅查询特定商品的当前适用促销
    2. 缺唯一商品时要求用户明确商品
    3. 通过统一 ToolRuntime 调用 promotion_query_tool
    """

    intent_name = "promotion_query"

    def __init__(self):
        self.commerce = get_ecommerce_client()
        self.runtime = get_global_tool_runtime()
    
    async def execute(self, state: AgentState, runtime: AgentRuntimeContext) -> FlowResult:
        """
        执行促销查询（P0-04 修复后）

        流程：
        1. 确定唯一商品 ID（从当前任务或明确上下文）
        2. 缺商品时返回 WAITING_SLOT，不执行查询
        3. 有商品时通过 ToolRuntime 调用 promotion_query_tool

        P1-07 修复：返回 FlowResult
        P0 修复：从 runtime 获取 session_id, user_id, user_access_token

        Args:
            state: Agent 状态
            runtime: Runtime Context

        Returns:
            FlowResult: 统一的 Flow 执行结果
        """
        from customer_service.tools.models import ToolResult, ToolError

        session_id = runtime.session_id
        user_query = state.get("current_message", "")

        logger.info(f"[{session_id}] 🎁 PromotionQueryFlow: {user_query}")

        try:
            # P0-23 修复：从 v7 规范字段获取 product_id（统一使用 Pydantic 模型）
            # 1. 优先从 active_task.slots 获取
            product_id = None
            active_task = state.get("active_task")
            if active_task:
                slots = active_task.slots
                product_id = slots.get("product_id")

            # 2. 如果没有，从 conversation_focus 获取
            if not product_id:
                conversation_focus = state.get("conversation_focus")
                if conversation_focus:
                    if conversation_focus.entity_type == "product":
                        product_id = conversation_focus.entity_id

            # P0-04 修复：缺唯一商品时不执行全站查询，而是返回需要澄清
            if not product_id:
                logger.info(f"[{session_id}] ⚠️ 缺少商品 ID，需要用户明确商品")
                return FlowResult(
                    ready_for_response=False,
                    tool_result=ToolResult(
                        tool_name="promotion_query_flow",  # P0-27: 添加必填字段 tool_name
                        ok=True,
                        data={
                            "missing_slot": "product_id",
                            "clarification": "请问您想了解哪款商品的优惠？可以告诉我商品名称或编号。"
                        }
                    ),
                    dialogue_reason="clarify",
                    objects=[]
                )

            # 有唯一商品：通过 ToolRuntime 调用 promotion_query_tool
            logger.info(f"[{session_id}] ✅ 查询商品 {product_id} 的促销活动")

            # 构造 Tool 执行上下文（P0 修复：使用传入的 runtime）
            tool_context = ToolExecutionContext(
                runtime=runtime,
                intent=BusinessIntent.PROMOTION_QUERY,
            )

            # 调用 promotion_query_tool
            tool_result = await self.runtime.execute(
                name="promotion_query_tool",
                args={"product_id": product_id},
                context=tool_context,
            )

            items_count = len(tool_result.data.get('items', [])) if tool_result.ok else 0
            logger.info(
                f"[{session_id}] ToolResult: ok={tool_result.ok}, "
                f"items={items_count}"
            )

            # P1-07 修复：返回 FlowResult
            promotions = tool_result.data.get("items", []) if tool_result.ok else []

            return FlowResult(
                ready_for_response=True,
                tool_result=tool_result,
                dialogue_reason=None if tool_result.ok else "error",
                objects=promotions
            )

        except Exception as e:
            logger.error(f"[{runtime.session_id}] ❌ PromotionQueryFlow error: {e}", exc_info=True)
            return FlowResult(
                ready_for_response=True,
                tool_result=ToolResult(
                    tool_name="promotion_query_flow",  # P0-27: 添加必填字段 tool_name
                    ok=False,
                    error=ToolError(code="FLOW_ERROR", message=str(e), retryable=False),
                    data={}
                ),
                dialogue_reason="error",
                objects=[]
            )

