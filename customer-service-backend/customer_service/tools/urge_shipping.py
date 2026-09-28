from __future__ import annotations

from pydantic import BaseModel, Field

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class UrgeShippingInput(BaseModel):
    order_id: str
    reason_code: str = "NORMAL_URGE"
    reason_detail: str = Field(default="用户希望尽快发出")


def build_urge_shipping_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: UrgeShippingInput, context: ToolExecutionContext) -> ToolResult:
        token = context.runtime.user_access_token.get_secret_value()
        # P1-50 修复：传递 request_id
        data = await client.create_shipping_urge(
            args.order_id,
            {"reason_code": args.reason_code, "reason_detail": args.reason_detail},
            token,
            idempotency_key=context.runtime.request_id,
            request_id=context.runtime.request_id,  # P1-50: 传递 request_id
        )
        return ToolResult(
            tool_name="urge_shipping_tool",
            ok=True,
            data=data,
            evidence=[
                EvidenceItem(
                    source_type="commerce_api",
                    source_name="create_shipping_urge",
                    reference_id=data.get("shipping_urge_request_id") or data.get("request_id"),
                    facts=data,
                )
            ],
            side_effect=True,
        )

    return ToolSpec(
        name="urge_shipping_tool",
        allowed_intents=("urge_shipping",),
        side_effect=True,
        timeout_seconds=8.0,
        retry_policy=RetryPolicy.WRITE_SAME_IDEMPOTENCY_KEY,
        args_model=UrgeShippingInput,
        handler=handler,
    )

