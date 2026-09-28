from __future__ import annotations

import logging
from pydantic import BaseModel

from customer_service.clients.ecommerce import EcommerceClient
from customer_service.tools.base import EvidenceItem, RetryPolicy, ToolExecutionContext, ToolResult, ToolSpec

logger = logging.getLogger(__name__)


class SizeRecommendInput(BaseModel):
    product_id: str
    height_cm: int | None = None
    weight_kg: int | None = None
    bust_cm: int | None = None
    waist_cm: int | None = None
    hip_cm: int | None = None
    fit_preference: str | None = "regular"


def _pick_size(args: SizeRecommendInput, available_sizes: list[str]) -> tuple[str | None, float, list[str]]:
    """
    完整的尺码推荐算法

    Returns:
        (推荐尺码, 置信度, 匹配原因列表)
    """
    if not available_sizes:
        return None, 0.0, []

    ordered = ["XS", "S", "M", "L", "XL", "XXL", "XXXL"]
    reason_codes = []
    confidence_scores = []

    # 如果没有任何体型数据，返回第一个可用尺码
    if not any([args.height_cm, args.weight_kg, args.bust_cm, args.waist_cm, args.hip_cm]):
        logger.warning("No body measurements provided, returning first available size")
        return available_sizes[0], 0.3, ["DEFAULT_AVAILABLE_SIZE"]

    # 1. 基于体重的初步判断（基础分）
    target_by_weight = None
    if args.weight_kg:
        if args.weight_kg <= 45:
            target_by_weight = "XS"
        elif args.weight_kg <= 52:
            target_by_weight = "S"
        elif args.weight_kg <= 62:
            target_by_weight = "M"
        elif args.weight_kg <= 75:
            target_by_weight = "L"
        elif args.weight_kg <= 88:
            target_by_weight = "XL"
        else:
            target_by_weight = "XXL"
        reason_codes.append("WEIGHT_MATCH")
        confidence_scores.append(0.65)

    # 2. 基于身高的修正
    if args.height_cm and args.weight_kg:
        bmi = args.weight_kg / ((args.height_cm / 100) ** 2)

        # BMI < 18.5: 偏瘦，可能需要小一码
        if bmi < 18.5 and target_by_weight:
            idx = ordered.index(target_by_weight)
            if idx > 0:
                target_by_weight = ordered[idx - 1]
            reason_codes.append("BMI_ADJUSTED_DOWN")

        # BMI > 25: 偏胖，可能需要大一码
        elif bmi > 25 and target_by_weight:
            idx = ordered.index(target_by_weight)
            if idx < len(ordered) - 1:
                target_by_weight = ordered[idx + 1]
            reason_codes.append("BMI_ADJUSTED_UP")

        reason_codes.append("HEIGHT_MATCH")
        confidence_scores.append(0.75)

    # 3. 基于胸围、腰围、臀围的精确匹配
    detailed_match = False
    if args.bust_cm and args.waist_cm:
        # 女装上衣尺码对照（标准尺码表）
        if args.bust_cm <= 82 and args.waist_cm <= 64:
            target_by_measurements = "S"
        elif args.bust_cm <= 86 and args.waist_cm <= 68:
            target_by_measurements = "M"
        elif args.bust_cm <= 90 and args.waist_cm <= 72:
            target_by_measurements = "L"
        elif args.bust_cm <= 94 and args.waist_cm <= 76:
            target_by_measurements = "XL"
        else:
            target_by_measurements = "XXL"

        # 如果三围数据完整，优先使用三围匹配结果
        if args.hip_cm:
            target_by_weight = target_by_measurements
            reason_codes.append("BUST_WAIST_HIP_MATCH")
            confidence_scores.append(0.92)
            detailed_match = True
        else:
            target_by_weight = target_by_measurements
            reason_codes.append("BUST_WAIST_MATCH")
            confidence_scores.append(0.85)
            detailed_match = True

    # 4. 版型偏好调整
    if target_by_weight and args.fit_preference:
        if args.fit_preference == "loose" and target_by_weight in ordered:
            idx = ordered.index(target_by_weight)
            if idx < len(ordered) - 1:
                target_by_weight = ordered[idx + 1]
                reason_codes.append("FIT_PREFERENCE_LOOSE")
        elif args.fit_preference == "tight" and target_by_weight in ordered:
            idx = ordered.index(target_by_weight)
            if idx > 0:
                target_by_weight = ordered[idx - 1]
                reason_codes.append("FIT_PREFERENCE_TIGHT")

    # 5. 检查推荐尺码是否在可用列表中
    if target_by_weight and target_by_weight in available_sizes:
        final_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.5
        return target_by_weight, min(final_confidence, 0.95), reason_codes

    # 6. 如果推荐尺码不可用，选择最接近的
    if target_by_weight and target_by_weight in ordered:
        target_idx = ordered.index(target_by_weight)
        for offset in [1, -1, 2, -2]:
            fallback_idx = target_idx + offset
            if 0 <= fallback_idx < len(ordered) and ordered[fallback_idx] in available_sizes:
                reason_codes.append("CLOSEST_AVAILABLE")
                final_confidence = sum(confidence_scores) / len(confidence_scores) * 0.8 if confidence_scores else 0.4
                return ordered[fallback_idx], final_confidence, reason_codes

    # 7. 降级：返回第一个可用尺码
    logger.warning(f"No matching size found, returning first available: {available_sizes[0]}")
    return available_sizes[0], 0.35, ["DEFAULT_AVAILABLE_SIZE"]


def build_size_recommend_tool(client: EcommerceClient) -> ToolSpec:
    async def handler(args: SizeRecommendInput, context: ToolExecutionContext) -> ToolResult:
        # 获取商品的所有 SKU
        skus = await client.get_skus(args.product_id)
        available = [sku for sku in skus if sku.get("stock_status") == "有货"]
        sizes = list(dict.fromkeys([sku.get("size_code") for sku in available if sku.get("size_code")]))

        # 使用完整算法推荐尺码
        recommended_size, confidence, reason_codes = _pick_size(args, sizes)

        # 找到对应的 SKU
        sku = next((item for item in available if item.get("size_code") == recommended_size), None)

        # 获取尺码图
        chart = await client.get_size_chart(args.product_id)

        # 构建详细的推荐结果
        result_data = {
            "recommended_size": recommended_size,
            "confidence": confidence,
            "reason_codes": reason_codes,
            "sku": sku,
            "size_chart_url": chart.get("image_url"),
            "available_sizes": sizes,
            "body_measurements_used": {
                "height_cm": args.height_cm,
                "weight_kg": args.weight_kg,
                "bust_cm": args.bust_cm,
                "waist_cm": args.waist_cm,
                "hip_cm": args.hip_cm,
                "fit_preference": args.fit_preference,
            },
        }

        # 构建证据链
        evidence = [
            EvidenceItem(
                source_type="commerce_api",
                source_name="get_skus",
                reference_id=sku.get("sku_id") if sku else args.product_id,
                facts={"sku": sku, "available_sizes": sizes},
            ),
            EvidenceItem(
                source_type="derived",
                source_name="legacy_size_recommendation_pending_slice_03",
                reference_id=args.product_id,
                facts={"confidence": confidence, "reason_codes": reason_codes},
            ),
        ]

        logger.info(f"Size recommendation: {recommended_size} (confidence={confidence:.2f}, reasons={reason_codes})")

        return ToolResult(
            tool_name="size_recommend_tool",
            ok=True,
            data=result_data,
            evidence=evidence,
        )

    return ToolSpec(
        name="size_recommend_tool",
        allowed_intents=("size_recommend",),
        side_effect=False,
        timeout_seconds=8.0,
        retry_policy=RetryPolicy.READ_ONCE_RETRY,
        args_model=SizeRecommendInput,
        handler=handler,
    )
