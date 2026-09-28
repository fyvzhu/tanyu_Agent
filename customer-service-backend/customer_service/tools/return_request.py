from __future__ import annotations

from pydantic import BaseModel

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class ReturnRequestInput(BaseModel):
    order_id: str
    product_id: str
    sku_id: str
    reason: str


def build_return_request_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: ReturnRequestInput, context: ToolExecutionContext) -> ToolResult:
        token = context.runtime.user_access_token.get_secret_value()
        # P1-50 修复：传递 request_id
        data = await client.create_return(
            args.order_id,
            {"product_id": args.product_id, "sku_id": args.sku_id, "reason": args.reason},
            token,
            idempotency_key=context.runtime.request_id,
            request_id=context.runtime.request_id,  # P1-50: 传递 request_id
        )
        return ToolResult(
            tool_name="return_request_tool",
            ok=True,
            data=data,
            evidence=[
                EvidenceItem(
                    source_type="commerce_api",
                    source_name="create_return",
                    reference_id=data.get("return_request_id") or data.get("request_id"),
                    facts=data,
                )
            ],
            side_effect=True,
        )

    return ToolSpec(
        name="return_request_tool",
        allowed_intents=("return",),
        side_effect=True,
        timeout_seconds=8.0,
        retry_policy=RetryPolicy.WRITE_SAME_IDEMPOTENCY_KEY,
        args_model=ReturnRequestInput,
        handler=handler,
    )
