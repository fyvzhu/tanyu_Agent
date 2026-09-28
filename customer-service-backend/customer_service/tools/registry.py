from __future__ import annotations

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.retrieval.service import ProductRetrievalService
from customer_service.tools.exchange_request import build_exchange_request_tool
from customer_service.tools.logistics_query import build_logistics_query_tool
from customer_service.tools.product_search import build_product_search_tool
from customer_service.tools.promotion_query import build_promotion_query_tool
from customer_service.tools.return_request import build_return_request_tool
from customer_service.tools.selling_point import build_selling_point_tool
from customer_service.tools.size_recommend import build_size_recommend_tool
from customer_service.tools.runtime import ToolRegistry, ToolRuntime
from customer_service.tools.urge_shipping import build_urge_shipping_tool


EXPECTED_BUSINESS_TOOLS = {
    "product_search_tool",
    "selling_point_tool",
    "size_recommend_tool",
    "promotion_query_tool",
    "logistics_query_tool",
    "return_request_tool",
    "exchange_request_tool",
    "urge_shipping_tool",
}


def build_default_tool_registry(
    client: EcommerceClient,
    retrieval: ProductRetrievalService | None = None,
) -> ToolRegistry:
    registry = ToolRegistry()
    for spec in (
        build_product_search_tool(client, retrieval),
        build_selling_point_tool(client),
        build_size_recommend_tool(client),
        build_promotion_query_tool(client),
        build_logistics_query_tool(client),
        build_return_request_tool(client),
        build_exchange_request_tool(client),
        build_urge_shipping_tool(client),
    ):
        registry.register(spec)

    missing = EXPECTED_BUSINESS_TOOLS - registry.names()
    extra = registry.names() - EXPECTED_BUSINESS_TOOLS
    if missing or extra:
        raise RuntimeError(f"tool registry mismatch: missing={missing}, extra={extra}")
    return registry


_global_registry = ToolRegistry()
_global_runtime = ToolRuntime(_global_registry)


def get_global_tool_registry() -> ToolRegistry:
    return _global_registry


def get_global_tool_runtime() -> ToolRuntime:
    return _global_runtime
