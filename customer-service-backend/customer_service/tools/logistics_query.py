from __future__ import annotations

from pydantic import BaseModel

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class LogisticsQueryInput(BaseModel):
    order_id: str


def build_logistics_query_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: LogisticsQueryInput, context: ToolExecutionContext) -> ToolResult:
        token = context.runtime.user_access_token.get_secret_value()
        data = await client.logistics(args.order_id, token)
        return ToolResult(
            tool_name="logistics_query_tool",
            ok=True,
            data=data,
            evidence=[
                EvidenceItem(
                    source_type="commerce_api",
                    source_name="get_logistics",
                    reference_id=args.order_id,
                    facts=data,
                )
            ],
        )

    return ToolSpec(
        name="logistics_query_tool",
        allowed_intents=("logistics_query",),
        side_effect=False,
        timeout_seconds=5.0,
        retry_policy=RetryPolicy.READ_ONCE_RETRY,
        args_model=LogisticsQueryInput,
        handler=handler,
    )
