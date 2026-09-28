from __future__ import annotations

from pydantic import BaseModel

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class ExchangeRequestInput(BaseModel):
    order_id: str
    product_id: str
    original_sku_id: str
    exchange_sku_id: str
    reason: str


def build_exchange_request_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: ExchangeRequestInput, context: ToolExecutionContext) -> ToolResult:
        token = context.runtime.user_access_token.get_secret_value()
        # P1-50 修复：传递 request_id
        data = await client.create_exchange(
            args.order_id,
            {
                "product_id": args.product_id,
                "original_sku_id": args.original_sku_id,
                "exchange_sku_id": args.exchange_sku_id,
                "reason": args.reason,
            },
            token,
            idempotency_key=context.runtime.request_id,
            request_id=context.runtime.request_id,  # P1-50: 传递 request_id
        )
        return ToolResult(
            tool_name="exchange_request_tool",
            ok=True,
            data=data,
            evidence=[
                EvidenceItem(
                    source_type="commerce_api",
                    source_name="create_exchange",
                    reference_id=data.get("exchange_request_id") or data.get("request_id"),
                    facts=data,
                )
            ],
            side_effect=True,
        )

    return ToolSpec(
        name="exchange_request_tool",
        allowed_intents=("exchange",),
        side_effect=True,
        timeout_seconds=8.0,
        retry_policy=RetryPolicy.WRITE_SAME_IDEMPOTENCY_KEY,
        args_model=ExchangeRequestInput,
        handler=handler,
    )
