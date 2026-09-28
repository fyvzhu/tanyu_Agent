from __future__ import annotations

from pydantic import BaseModel

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class SellingPointInput(BaseModel):
    product_id: str
    user_need: str | None = None
    include_promotion: bool = True


def build_selling_point_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: SellingPointInput, context: ToolExecutionContext) -> ToolResult:
        card = await client.knowledge_card(args.product_id)
        promotions = await client.active_promotions(args.product_id) if args.include_promotion else []
        facts = {
            "product": card,
            "promotions": promotions,
        }
        return ToolResult(
            tool_name="selling_point_tool",
            ok=True,
            data=facts,
            evidence=[
                EvidenceItem(
                    source_type="commerce_api",
                    source_name="knowledge_card",
                    reference_id=args.product_id,
                    facts={"product_id": args.product_id},
                ),
                *[
                    EvidenceItem(
                        source_type="commerce_api",
                        source_name="promotion",
                        reference_id=promo.get("promotion_id"),
                        facts=promo,
                    )
                    for promo in promotions
                ],
            ],
        )

    return ToolSpec(
        name="selling_point_tool",
        allowed_intents=("product_query",),
        side_effect=False,
        timeout_seconds=5.0,
        retry_policy=RetryPolicy.READ_ONCE_RETRY,
        args_model=SellingPointInput,
        handler=handler,
    )
