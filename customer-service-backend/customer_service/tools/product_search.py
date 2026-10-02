from __future__ import annotations

from decimal import Decimal

from loguru import logger
from pydantic import BaseModel, Field

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.retrieval.service import ProductRetrievalService, sku_filter_payload
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec


class ProductSearchInput(BaseModel):
    query: str
    category: str | None = None
    brand: str | None = None
    color: str | None = None
    size: str | None = None
    min_price: Decimal | None = None
    max_price: Decimal | None = None
    usage: str | None = None
    in_stock_only: bool = True
    top_k: int = Field(default=5, ge=1, le=20)


def build_product_search_tool(client: EcommerceClient, retrieval: ProductRetrievalService | None = None) -> ToolSpec:
    async def handler(args: ProductSearchInput, context: ToolExecutionContext) -> ToolResult:
        # 尝试使用 RAG 检索（Qdrant + Elasticsearch）
        retrieval_outcome = await retrieval.retrieve(args.query, limit=max(args.top_k * 4, 20)) if retrieval else None
        product_ids = retrieval_outcome.product_ids if retrieval_outcome else None

        # 路径 1: RAG 检索成功，使用 product_ids 过滤
        if product_ids:
            # 调用标准化的SKU Filter API（使用布尔值而非"有货"字符串）
            filter_payload = {
                "product_ids": product_ids,
                "colors": [args.color] if args.color else None,
                "sizes": [args.size] if args.size else None,
                "in_stock": True if args.in_stock_only else None,
            }
            skus = await client.filter_skus(filter_payload)

            # P1-05 修复：用户硬约束不可静默放宽
            # 如果严格匹配为空，返回明确说明，不自动放宽
            # 注意：brand/category 在 RAG 阶段已生效，这里主要检查 SKU 级别的硬约束
            if not skus and (args.color or args.size or args.min_price or args.max_price):
                logger.warning(
                    f"⚠️ 严格约束下无匹配结果 - "
                    f"brand={args.brand}, category={args.category}, "
                    f"color={args.color}, size={args.size}, "
                    f"price=[{args.min_price}, {args.max_price}]"
                )
                return ToolResult(
                    tool_name="product_search_tool",
                    ok=True,
                    data={
                        "retrieval_mode": retrieval_outcome.mode if retrieval_outcome else "rag",
                        "candidates": [],
                        "strict_match_failed": True,
                        "applied_filters": {
                            "brand": args.brand,
                            "category": args.category,
                            "color": args.color,
                            "size": args.size,
                            "min_price": str(args.min_price) if args.min_price else None,
                            "max_price": str(args.max_price) if args.max_price else None,
                        },
                    },
                    evidence=[
                        EvidenceItem(
                            source_type="rag",
                            source_name="strict_filter",
                            reference_id="no_match",
                            facts={"reason": "no_products_match_strict_filters", "filters": filter_payload},
                        )
                    ],
                )

            # 批量获取商品信息
            products = {
                item["product_id"]: item
                for item in await client.batch_get_products(list(dict.fromkeys(sku["product_id"] for sku in skus)))
            }

            # 组装候选商品（包含主图和价格范围）
            candidates = []
            for sku in skus:
                product = products.get(sku["product_id"])
                if not product:
                    continue
                product_id = sku["product_id"]
                candidates.append(
                    {
                        "product_id": product_id,
                        "brand": product.get("brand"),
                        "product_display_name": product.get("product_display_name"),
                        "category": product.get("category"),
                        "main_image_url": product.get("main_image_url"),
                        "min_price": product.get("min_price"),
                        "max_price": product.get("max_price"),
                        "has_stock": product.get("has_stock"),
                        "selected_sku": sku,
                        "score": retrieval_outcome.scores.get(product_id, 0.0),
                        "matched_reasons": retrieval_outcome.matched_reasons.get(product_id, []),
                    }
                )
                if len(candidates) >= args.top_k:
                    break

            mode = retrieval_outcome.mode
            evidence = retrieval_outcome.evidence + [
                {"source": "commerce", "sku_id": item["selected_sku"].get("sku_id"), "product_id": item["product_id"]}
                for item in candidates
            ]

        # 路径 2: RAG 失败，降级到 Commerce-only 模式
        else:
            logger.warning("RAG retrieval failed or unavailable, falling back to Commerce-only search")
            # 构造参数，过滤掉 None 值（Commerce API 不接受 None）
            search_params = {
                "page": 1,
                "page_size": args.top_k,
            }
            if args.query:
                search_params["q"] = args.query
            if args.brand:
                search_params["brand"] = args.brand
            if args.category:
                search_params["category"] = args.category
            if args.color:
                search_params["color"] = args.color
            if args.size:
                search_params["size"] = args.size
            if args.min_price is not None:
                search_params["min_price"] = str(args.min_price)
            if args.max_price is not None:
                search_params["max_price"] = str(args.max_price)
            if args.in_stock_only is not None:
                search_params["in_stock"] = args.in_stock_only

            data = await client.search_products(search_params)
            # P7 修复: Commerce-only 路径需要统一 candidate 结构
            # ProductListItem 没有 selected_sku，需要手动组装
            items = data.get("items", [])
            candidates = []
            for item in items:
                # 为 Commerce-only 路径补充统一结构，确保与 RAG 路径一致
                candidates.append({
                    "product_id": item.get("product_id"),
                    "brand": item.get("brand"),
                    "product_display_name": item.get("product_display_name"),
                    "category": item.get("category"),
                    "main_image_url": item.get("main_image_url"),
                    "min_price": item.get("min_price"),
                    "max_price": item.get("max_price"),
                    "has_stock": item.get("has_stock"),
                    "selected_sku": None,  # Commerce-only 路径无具体 SKU
                    "score": 0.0,
                    "matched_reasons": ["commerce_search"],
                })

            # P1-05 修复：Commerce-only 模式下，严格匹配为空也不放宽
            # 检查所有硬约束：brand, category, color, size, price
            if not candidates and (args.brand or args.category or args.color or args.size or args.min_price or args.max_price):
                logger.warning(
                    f"⚠️ Commerce-only 严格约束下无匹配结果 - "
                    f"brand={args.brand}, category={args.category}, "
                    f"color={args.color}, size={args.size}, "
                    f"price=[{args.min_price}, {args.max_price}]"
                )
                return ToolResult(
                    tool_name="product_search_tool",
                    ok=True,
                    data={
                        "retrieval_mode": "commerce_only_degraded",
                        "candidates": [],
                        "strict_match_failed": True,
                        "applied_filters": {
                            "query": args.query,
                            "brand": args.brand,
                            "category": args.category,
                            "color": args.color,
                            "size": args.size,
                            "min_price": str(args.min_price) if args.min_price else None,
                            "max_price": str(args.max_price) if args.max_price else None,
                        },
                    },
                    evidence=[
                        EvidenceItem(
                            source_type="commerce_api",
                            source_name="strict_search",
                            reference_id="no_match",
                            facts={"reason": "no_products_match_commerce_filters", "degraded": True},
                        )
                    ],
                )

            mode = "commerce_only_degraded"
            evidence = [
                {"source": "commerce", "degraded": True, "reason": "rag_unavailable"},
                *[{"source": "commerce", "product_id": item.get("product_id")} for item in candidates]
            ]

        return ToolResult(
            tool_name="product_search_tool",
            ok=True,
            data={"retrieval_mode": mode, "candidates": candidates},
            evidence=[
                EvidenceItem(
                    source_type="commerce_api" if item.get("source") == "commerce" else "rag",
                    source_name=str(item.get("source", "retrieval")),
                    reference_id=item.get("product_id") or item.get("sku_id"),
                    facts=item,
                )
                for item in evidence
            ],
        )

    return ToolSpec(
        name="product_search_tool",
        allowed_intents=("product_query",),
        side_effect=False,
        timeout_seconds=8.0,
        retry_policy=RetryPolicy.READ_ONCE_RETRY,
        args_model=ProductSearchInput,
        handler=handler,
    )
