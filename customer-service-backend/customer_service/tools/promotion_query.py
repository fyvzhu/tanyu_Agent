from __future__ import annotations

from pydantic import BaseModel

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class PromotionQueryInput(BaseModel):
    """
    促销查询输入（P1-04 修复）

    仅接受 product_id，member_level 由 Commerce 从 JWT sub 自动获取
    """
    product_id: str


def build_promotion_query_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: PromotionQueryInput, context: ToolExecutionContext) -> ToolResult:
        """
        查询商品促销（P1-04 修复）

        使用当前用户的 Access JWT 调用 Commerce API
        Commerce 从 JWT sub 自动查询真实用户等级并过滤促销

        P0-13 修复：使用 context.runtime.user_access_token
        P1-50 修复：传递 request_id
        """
        # P1-04 修复：使用用户 JWT，让 Commerce 自动获取 member_level
        # 获取实际的token字符串（而非SecretStr对象）
        user_token = context.runtime.user_access_token.get_secret_value()

        promotions = await client.active_promotions(
            product_id=args.product_id,
            user_access_token=user_token,
            request_id=context.runtime.request_id,  # P1-50: 传递 request_id
        )
        # P0-14 修复：统一使用 "items" 字段，不再使用 "promotions"
        return ToolResult(
            tool_name="promotion_query_tool",
            ok=True,
            data={"product_id": args.product_id, "items": promotions},
            evidence=[
                EvidenceItem(
                    source_type="commerce_api",
                    source_name="promotion",
                    reference_id=item.get("promotion_id"),
                    facts=item,
                )
                for item in promotions
            ],
        )

    return ToolSpec(
        name="promotion_query_tool",
        allowed_intents=("promotion_query",),
        side_effect=False,
        timeout_seconds=5.0,
        retry_policy=RetryPolicy.READ_ONCE_RETRY,
        args_model=PromotionQueryInput,
        handler=handler,
    )
