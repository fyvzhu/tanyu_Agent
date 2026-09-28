from __future__ import annotations

from typing import Any


REQUIRED_SLOTS: dict[str, list[str]] = {
    "product_query": [],
    "size_recommend": ["product_id"],
    "urge_order_payment": ["product_id"],
    "promotion_query": ["product_id"],
    "logistics_query": ["order_id"],
    "return": ["order_id", "product_id", "sku_id", "reason"],
    "exchange": ["order_id", "product_id", "original_sku_id", "exchange_sku_id", "reason"],
    "chitchat": [],
    "other": [],
}


INTENT_TOOL: dict[str, str | None] = {
    "product_query": "product_search_tool",
    "size_recommend": "size_recommend_tool",
    "urge_order_payment": None,
    "promotion_query": "promotion_query_tool",
    "logistics_query": "logistics_query_tool",
    "return": "return_request_tool",
    "exchange": "exchange_request_tool",
    "chitchat": None,
    "other": None,
}


def missing_slots(intent: str, slots: dict[str, Any]) -> list[str]:
    return [slot for slot in REQUIRED_SLOTS.get(intent, []) if not slots.get(slot)]


def selected_tool(intent: str, slots: dict[str, Any]) -> str | None:
    if intent == "product_query" and slots.get("product_id"):
        return "selling_point_tool"
    return INTENT_TOOL.get(intent)
