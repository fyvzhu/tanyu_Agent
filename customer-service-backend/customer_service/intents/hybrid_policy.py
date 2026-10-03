"""
Hybrid NLU Policy - NLU_HYBRID_REFACTOR

职责：根据规则意图置信度、margin、实体完整性决定是否需要调用 LLM。
禁止：把 confidence 阈值逻辑散落到 routing.py 或 intent_parse.py 中。

根据 NLU_HYBRID_REFACTOR.md 第9节：
- HIGH：confidence >= 0.85 AND margin >= 0.20 AND 无歧义 → 默认不为意图调用 LLM
- MEDIUM：0.60 <= confidence < 0.85 → LLM 验证/融合
- LOW：confidence < 0.60 OR margin < 0.08 → LLM 作为主要语义判定

所有阈值做成配置项，不硬编码。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from loguru import logger


class ConfidenceLevel(str, Enum):
    """规则意图置信度等级"""
    HIGH = "high"      # 规则高置信度，默认不调用 LLM（除非实体缺失）
    MEDIUM = "medium"  # 中置信度，调用 LLM 融合
    LOW = "low"        # 低置信度，LLM 作为主要来源


@dataclass
class HybridNLUSettings:
    """
    Hybrid NLU 阈值配置（全部可从 settings 覆盖）

    NLU_HYBRID_REFACTOR 第9节：阈值必须做成配置项，不允许散落硬编码。
    """
    # 规则置信度阈值
    rule_high_confidence: float = 0.85
    rule_medium_confidence: float = 0.60
    rule_min_margin: float = 0.08

    # LLM 意图采用阈值
    llm_accept_confidence: float = 0.75

    # 冲突处理：LLM 意图优于规则的条件
    conflict_llm_min: float = 0.85   # LLM 置信度至少要达到此值才能覆盖规则
    conflict_rule_max: float = 0.75  # 规则置信度低于此值，才允许 LLM 覆盖

    # 是否为高置信规则启用"仅为实体补全调用 LLM"
    entity_only_llm_for_high_rule: bool = True


# 默认单例（全局共享）
DEFAULT_SETTINGS = HybridNLUSettings()


@dataclass
class LLMCallDecision:
    """是否需要调用 LLM 的决策结果"""
    should_call: bool
    level: ConfidenceLevel
    for_entity_only: bool = False   # True 表示仅为实体补全调用 LLM，不更新意图
    reason: str = ""


def evaluate_confidence_level(
    confidence: float,
    margin: float | None,
    settings: HybridNLUSettings | None = None,
) -> ConfidenceLevel:
    """
    将规则 confidence/margin 映射到 ConfidenceLevel。

    Args:
        confidence: 规则分类器的 top 置信度
        margin: top1 - top2 置信度差值（None 表示只有一个候选）
        settings: 阈值配置（None 使用默认）
    """
    cfg = settings or DEFAULT_SETTINGS
    effective_margin = margin if margin is not None else 1.0

    if confidence >= cfg.rule_high_confidence and effective_margin >= cfg.rule_min_margin:
        return ConfidenceLevel.HIGH
    elif confidence >= cfg.rule_medium_confidence:
        return ConfidenceLevel.MEDIUM
    else:
        return ConfidenceLevel.LOW


def should_call_llm(
    confidence: float,
    margin: float | None,
    ambiguous: bool,
    required_entities: list[str],
    extracted_entities: dict[str, Any],
    settings: HybridNLUSettings | None = None,
) -> LLMCallDecision:
    """
    决定是否需要调用 LLM。

    NLU_HYBRID_REFACTOR 第9节：needs_llm 不能只看 intent confidence，
    还要同时考虑 entity completeness 和 context unresolved。

    Args:
        confidence: 规则意图置信度
        margin: 置信度差值
        ambiguous: 是否有歧义（规则检测到多意图）
        required_entities: 该意图需要的核心实体（如 product_id/brand）
        extracted_entities: 规则已提取的实体
        settings: 阈值配置
    """
    cfg = settings or DEFAULT_SETTINGS
    level = evaluate_confidence_level(confidence, margin, cfg)

    if ambiguous:
        logger.debug("[HybridPolicy] 检测到歧义 → 调用 LLM")
        return LLMCallDecision(
            should_call=True, level=level,
            reason="ambiguous intent, need LLM to disambiguate",
        )

    if level == ConfidenceLevel.LOW:
        return LLMCallDecision(
            should_call=True, level=level,
            reason=f"low confidence({confidence:.2f}), LLM as primary source",
        )

    if level == ConfidenceLevel.MEDIUM:
        return LLMCallDecision(
            should_call=True, level=level,
            reason=f"medium confidence({confidence:.2f}), LLM for verification",
        )

    # HIGH - 默认不调用 LLM，但检查核心实体是否缺失
    if cfg.entity_only_llm_for_high_rule and required_entities:
        missing_core = [e for e in required_entities if e not in extracted_entities]
        if missing_core:
            logger.debug(f"[HybridPolicy] Rule HIGH，但核心实体缺失 {missing_core}，为实体补全调用 LLM")
            return LLMCallDecision(
                should_call=True, level=level, for_entity_only=True,
                reason=f"high confidence rule, but missing core entities: {missing_core}",
            )

    return LLMCallDecision(
        should_call=False, level=level,
        reason=f"high confidence({confidence:.2f}), skip LLM",
    )


def fuse_intent(
    rule_intent: str | None,
    rule_confidence: float,
    llm_intent: str | None,
    llm_confidence: float,
    level: ConfidenceLevel,
    settings: HybridNLUSettings | None = None,
) -> tuple[str | None, float, str]:
    """
    融合规则意图与 LLM 意图，返回 (final_intent, final_confidence, source)。

    NLU_HYBRID_REFACTOR 第10节：
    - Rule HIGH，LLM 未调用 → 用规则
    - Rule MEDIUM，LLM 与规则一致 → max(rule, llm) + 0.03，上限 0.98
    - Rule 与 LLM 冲突 → 条件性采用 LLM 或 CLARIFY（返回 None）
    - 两个结果都 >= 0.80 但不一致 → 必须 CLARIFY
    """
    cfg = settings or DEFAULT_SETTINGS

    # LLM 未调用（HIGH 直接用规则）
    if llm_intent is None:
        return rule_intent, rule_confidence, "rule"

    # 一致
    if rule_intent == llm_intent:
        if level == ConfidenceLevel.HIGH:
            return rule_intent, rule_confidence, "rule"
        # MEDIUM / LOW + 一致
        boosted = min(max(rule_confidence, llm_confidence) + 0.03, 0.98)
        return rule_intent, boosted, "rule+llm"

    # 冲突处理
    both_high = rule_confidence >= 0.80 and llm_confidence >= 0.80
    if both_high:
        # 两个都高但冲突 → 必须澄清
        logger.info(
            f"[HybridPolicy] 意图冲突且双方均高置信度 "
            f"rule={rule_intent}({rule_confidence:.2f}) "
            f"llm={llm_intent}({llm_confidence:.2f}) → CLARIFY"
        )
        return None, max(rule_confidence, llm_confidence), "rule+llm"

    # LLM 明显更可信，且规则置信度偏低
    if (llm_confidence >= cfg.conflict_llm_min
            and rule_confidence < cfg.conflict_rule_max):
        logger.info(
            f"[HybridPolicy] 冲突，采用 LLM 意图 {llm_intent}({llm_confidence:.2f})"
        )
        return llm_intent, llm_confidence, "llm"

    # 其他冲突 → CLARIFY
    logger.info(
        f"[HybridPolicy] 意图冲突 rule={rule_intent}({rule_confidence:.2f}) "
        f"llm={llm_intent}({llm_confidence:.2f}) → CLARIFY"
    )
    return None, max(rule_confidence, llm_confidence), "rule+llm"
