"""
Entity Fusion Service - NLU_HYBRID_REFACTOR

职责：将规则实体、LLM 实体、上下文实体按优先级融合为最终实体字典。

融合顺序（NLU_HYBRID_REFACTOR 第11节）：
  Validated Exact Rule
      > Catalog Exact
      > Context Confirmed
      > Rule Dictionary/Regex
      > High-confidence LLM
      > Low-confidence LLM

禁止：
- 不允许 dict.update() 直接覆盖规则实体
- product_id/order_id/sku_id 规则实体不允许被 LLM 幻觉覆盖
- 五类核心实体各有独立融合规则（第12节）
"""
from __future__ import annotations

from loguru import logger

from customer_service.intents.models import EntityCandidate


# 不允许 LLM 覆盖的确定性实体（NLU_HYBRID_REFACTOR 第13节）
_LLM_CANNOT_OVERRIDE_RULE = frozenset({
    "product_id",
    "order_id",
    "sku_id",
    "price",
    "max_price",
    "size",
    "color",
})

# 高置信度阈值（LLM 实体需达到此值才纳入融合）
_LLM_ENTITY_MIN_CONFIDENCE = 0.70


class EntityFusionService:
    """
    实体融合服务

    将来自不同来源的 EntityCandidate 按优先级合并，
    返回最终 dict[str, EntityCandidate]。
    """

    def merge(
        self,
        rule_entities: list[EntityCandidate],
        llm_entities: list[EntityCandidate],
        context_entities: list[EntityCandidate] | None = None,
    ) -> dict[str, EntityCandidate]:
        """
        三方融合：规则 + LLM + 上下文。

        Args:
            rule_entities: 规则提取的实体候选（优先级最高）
            llm_entities: LLM 提取的实体候选
            context_entities: 从上下文继承的实体（DialogueFrame / active_task.slots）

        Returns:
            dict[str, EntityCandidate] — 融合后的最终实体字典
        """
        final: dict[str, EntityCandidate] = {}

        # 第1步：上下文实体作为基线（最低优先级，可被覆盖）
        if context_entities:
            for ec in context_entities:
                if ec.value:
                    final[ec.name] = ec
                    logger.debug(f"[EntityFusion] 上下文实体: {ec.name}={ec.value} (source=context)")

        # 第2步：规则实体（优先级高于上下文）
        for rc in rule_entities:
            if not rc.value:
                continue
            existing = final.get(rc.name)
            if existing is None or existing.source in ("context",):
                final[rc.name] = rc
                logger.debug(f"[EntityFusion] 规则实体: {rc.name}={rc.value} (conf={rc.confidence:.2f})")
            elif rc.validated and not existing.validated:
                # 验证过的规则实体覆盖未验证的上下文实体
                final[rc.name] = rc
                logger.debug(f"[EntityFusion] 验证规则覆盖: {rc.name}={rc.value}")

        # 第3步：LLM 实体融合（受限合并）
        for lc in llm_entities:
            if not lc.value:
                continue
            if lc.confidence < _LLM_ENTITY_MIN_CONFIDENCE:
                logger.debug(
                    f"[EntityFusion] LLM 实体 {lc.name}={lc.value} "
                    f"置信度过低({lc.confidence:.2f})，跳过"
                )
                continue

            existing = final.get(lc.name)
            if existing is None:
                # 规则未提取，接受 LLM 结果
                final[lc.name] = lc
                logger.debug(f"[EntityFusion] LLM 新增实体: {lc.name}={lc.value}")
            elif existing.source in ("rule", "catalog") and lc.name in _LLM_CANNOT_OVERRIDE_RULE:
                # 规则确定性实体，LLM 不允许覆盖（第13节）
                if existing.value != lc.value:
                    logger.warning(
                        f"[EntityFusion] LLM 试图覆盖规则实体 "
                        f"{lc.name}: rule={existing.value} vs llm={lc.value}，已忽略 LLM"
                    )
            elif existing.source == "context" and lc.confidence >= _LLM_ENTITY_MIN_CONFIDENCE:
                # LLM 比上下文继承更可信
                final[lc.name] = lc
                logger.debug(f"[EntityFusion] LLM 覆盖上下文实体: {lc.name}={lc.value}")

        return final


def llm_entities_to_candidates(
    llm_entities: list[dict],
) -> list[EntityCandidate]:
    """
    将 LLM 输出的实体列表转换为 EntityCandidate。

    Args:
        llm_entities: [{"name": ..., "value": ..., "confidence": ..., "text_span": ...}]
    """
    candidates = []
    for e in llm_entities:
        name = e.get("name", "")
        value = e.get("value", "")
        if not name or not value:
            continue
        candidates.append(EntityCandidate(
            name=name,
            value=value,
            source="llm",
            confidence=float(e.get("confidence", 0.8)),
            text_span=e.get("text_span"),
        ))
    return candidates


def rule_entities_to_candidates(
    rule_dict: dict,
    base_confidence: float = 0.90,
) -> list[EntityCandidate]:
    """
    将规则 entity_extractor 的平铺字典转换为 EntityCandidate 列表。

    向后兼容：rule 层输出的仍然可能是旧的 dict[str, Any] 格式，
    这里统一包装成 EntityCandidate，source=rule，默认高置信度。

    Args:
        rule_dict: {"color": "黑色", "product_id": "29570", ...}
        base_confidence: 默认置信度（规则实体通常较高）
    """
    candidates = []

    # 不同实体类型的规则置信度（确定性越高越大）
    _confidence_map = {
        "product_id": 0.95,
        "order_id": 0.97,
        "sku_id": 0.95,
        "price": 0.92,
        "max_price": 0.92,
        "size": 0.90,
        "color": 0.88,
        "brand": 0.85,
        "product_name": 0.80,
        "height_cm": 0.90,
        "weight_kg": 0.90,
        "waist_cm": 0.90,
        "bust_cm": 0.90,
        "hip_cm": 0.90,
        "fit_preference": 0.85,
    }

    for name, value in rule_dict.items():
        if value is None or value == "":
            continue
        # 如果 value 本身已经是 EntityCandidate，直接使用
        if isinstance(value, EntityCandidate):
            candidates.append(value)
            continue
        confidence = _confidence_map.get(name, base_confidence)
        candidates.append(EntityCandidate(
            name=name,
            value=value,
            source="rule",
            confidence=confidence,
            text_span=None,
        ))
    return candidates
