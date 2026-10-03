"""
NLU_HYBRID_REFACTOR 单元测试（不依赖外部服务）

覆盖场景：
  A. Rule 高置信度，不调用 LLM
  B. Rule 中置信度决策
  C. Rule 与 LLM 冲突时 → CLARIFY（ambiguous）
  D. LLM Timeout → fallback_used=True，不 500
  E. 规则实体不可被 LLM 覆盖（product_id）
  F. Brand 抽取
  G. Product Name 粗抽取
  H. Price 抽取
  I. Entity Fusion 优先级
  J. HybridNLUSettings 阈值配置

全部为纯单元测试（mock LLM，不需要数据库/Redis/LLM 网络）。
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from customer_service.intents.models import EntityCandidate, HybridIntentResult
from customer_service.intents.hybrid_policy import (
    HybridNLUSettings,
    ConfidenceLevel,
    evaluate_confidence_level,
    should_call_llm,
    fuse_intent,
)
from customer_service.intents.entity_fusion import (
    EntityFusionService,
    rule_entities_to_candidates,
    llm_entities_to_candidates,
)
from customer_service.intents.entity_extractor import (
    extract_entities,
    extract_entities_with_candidates,
)
from customer_service.intents.classifier import IntentClassifier
from customer_service.tasking.models import BusinessIntent


# ──────────────────────────────────────────────────────────────
# A. Rule 高置信度 → should_call_llm = False
# ──────────────────────────────────────────────────────────────
class TestConfidenceLevel:

    def test_high_confidence(self):
        """confidence=0.91, margin=0.25 → HIGH"""
        level = evaluate_confidence_level(0.91, 0.25)
        assert level == ConfidenceLevel.HIGH

    def test_medium_confidence(self):
        """confidence=0.72, margin=0.18 → MEDIUM"""
        level = evaluate_confidence_level(0.72, 0.18)
        assert level == ConfidenceLevel.MEDIUM

    def test_low_confidence(self):
        """confidence=0.50 → LOW"""
        level = evaluate_confidence_level(0.50, 0.10)
        assert level == ConfidenceLevel.LOW

    def test_high_conf_small_margin_is_medium(self):
        """confidence=0.90 但 margin < 0.08 → MEDIUM（视为有歧义）"""
        level = evaluate_confidence_level(0.90, 0.05)
        assert level == ConfidenceLevel.MEDIUM


class TestShouldCallLLM:

    def test_high_rule_no_llm(self):
        """规则 HIGH 且无缺失实体 → 不调用 LLM"""
        decision = should_call_llm(
            confidence=0.91, margin=0.25, ambiguous=False,
            required_entities=[], extracted_entities={},
        )
        assert decision.should_call is False
        assert decision.level == ConfidenceLevel.HIGH

    def test_medium_rule_calls_llm(self):
        """规则 MEDIUM → 调用 LLM"""
        decision = should_call_llm(
            confidence=0.72, margin=0.18, ambiguous=False,
            required_entities=[], extracted_entities={},
        )
        assert decision.should_call is True
        assert decision.level == ConfidenceLevel.MEDIUM

    def test_low_rule_calls_llm(self):
        """规则 LOW → 调用 LLM"""
        decision = should_call_llm(
            confidence=0.45, margin=0.05, ambiguous=False,
            required_entities=[], extracted_entities={},
        )
        assert decision.should_call is True
        assert decision.level == ConfidenceLevel.LOW

    def test_ambiguous_always_calls_llm(self):
        """有歧义时，即便是 HIGH 也调用 LLM"""
        decision = should_call_llm(
            confidence=0.90, margin=0.25, ambiguous=True,
            required_entities=[], extracted_entities={},
        )
        assert decision.should_call is True

    def test_high_rule_missing_brand_calls_llm_for_entity(self):
        """规则 HIGH 但缺少 brand → 仅为实体补全调用 LLM"""
        decision = should_call_llm(
            confidence=0.90, margin=0.25, ambiguous=False,
            required_entities=["brand", "product_name"],
            extracted_entities={},  # 没有提取到 brand
        )
        assert decision.should_call is True
        assert decision.for_entity_only is True


# ──────────────────────────────────────────────────────────────
# C. Rule 与 LLM 冲突
# ──────────────────────────────────────────────────────────────
class TestFuseIntent:

    def test_consistent_intents_boosted(self):
        """Rule MEDIUM + LLM 一致 → 置信度提升"""
        intent, conf, source = fuse_intent(
            rule_intent="promotion_query", rule_confidence=0.72,
            llm_intent="promotion_query", llm_confidence=0.91,
            level=ConfidenceLevel.MEDIUM,
        )
        assert intent == "promotion_query"
        assert conf > 0.91  # 提升了
        assert "llm" in source

    def test_conflict_both_high_returns_none(self):
        """两者都高且冲突 → 返回 None（CLARIFY）"""
        intent, conf, source = fuse_intent(
            rule_intent="product_query", rule_confidence=0.82,
            llm_intent="promotion_query", llm_confidence=0.88,
            level=ConfidenceLevel.MEDIUM,
        )
        assert intent is None  # 必须澄清，不能静默选择

    def test_llm_wins_when_rule_low(self):
        """LLM 高且规则低 → 采用 LLM 意图"""
        intent, conf, source = fuse_intent(
            rule_intent="product_query", rule_confidence=0.62,
            llm_intent="promotion_query", llm_confidence=0.91,
            level=ConfidenceLevel.MEDIUM,
        )
        assert intent == "promotion_query"
        assert source == "llm"

    def test_high_rule_no_llm_keeps_rule(self):
        """Rule HIGH，LLM 未调用 → 用规则"""
        intent, conf, source = fuse_intent(
            rule_intent="logistics_query", rule_confidence=0.91,
            llm_intent=None, llm_confidence=0.0,
            level=ConfidenceLevel.HIGH,
        )
        assert intent == "logistics_query"
        assert source == "rule"


# ──────────────────────────────────────────────────────────────
# E. 规则实体不可被 LLM 覆盖（product_id / order_id）
# ──────────────────────────────────────────────────────────────
class TestEntityFusion:

    def test_rule_product_id_not_overridden_by_llm(self):
        """LLM 返回不同 product_id → 规则值保持不变（第13节）"""
        svc = EntityFusionService()
        rule_entities = rule_entities_to_candidates({"product_id": "29570"})
        llm_entities = llm_entities_to_candidates([
            {"name": "product_id", "value": "15970", "confidence": 0.92}
        ])
        result = svc.merge(rule_entities=rule_entities, llm_entities=llm_entities)
        assert result["product_id"].value == "29570"
        assert result["product_id"].source == "rule"

    def test_llm_adds_brand_when_rule_misses(self):
        """规则未提取 brand，LLM 可以补充（第12.4节）"""
        svc = EntityFusionService()
        rule_entities = rule_entities_to_candidates({"product_id": "29570"})
        llm_entities = llm_entities_to_candidates([
            {"name": "brand", "value": "Puma", "confidence": 0.88}
        ])
        result = svc.merge(rule_entities=rule_entities, llm_entities=llm_entities)
        assert result["product_id"].value == "29570"
        assert result["brand"].value == "Puma"
        assert result["brand"].source == "llm"

    def test_low_confidence_llm_entity_rejected(self):
        """LLM 置信度 < 0.70 的实体不纳入融合结果"""
        svc = EntityFusionService()
        llm_entities = llm_entities_to_candidates([
            {"name": "brand", "value": "Unknown", "confidence": 0.50}
        ])
        result = svc.merge(rule_entities=[], llm_entities=llm_entities)
        assert "brand" not in result

    def test_context_entity_overridden_by_rule(self):
        """上下文实体（旧值）被规则实体覆盖（融合优先级验证）"""
        svc = EntityFusionService()
        ctx = [EntityCandidate(name="product_id", value="11111", source="context", confidence=0.80)]
        rule_entities = rule_entities_to_candidates({"product_id": "29570"})
        result = svc.merge(rule_entities=rule_entities, llm_entities=[], context_entities=ctx)
        assert result["product_id"].value == "29570"
        assert result["product_id"].source == "rule"


# ──────────────────────────────────────────────────────────────
# F/G/H. 实体抽取（brand / product_name / price）
# ──────────────────────────────────────────────────────────────
class TestEntityExtractor:

    def test_brand_extraction_puma(self):
        """'有没有 Puma 的运动鞋？' → brand=Puma"""
        candidates = extract_entities_with_candidates("有没有 Puma 的运动鞋？")
        assert "brand" in candidates
        assert candidates["brand"].value == "Puma"
        assert candidates["brand"].source == "rule"
        assert candidates["brand"].validated is True

    def test_brand_extraction_just_natural(self):
        """'Just Natural 中性防雨夹克' → brand=Just Natural"""
        candidates = extract_entities_with_candidates("Just Natural 中性防雨夹克有活动吗？")
        assert "brand" in candidates
        assert candidates["brand"].value == "Just Natural"

    def test_product_name_extraction(self):
        """'防雨外套' 粗提取为 product_name"""
        candidates = extract_entities_with_candidates("那个防雨外套有没有 M 码？")
        assert "product_name" in candidates
        assert "外套" in candidates["product_name"].value

    def test_max_price_extraction(self):
        """'推荐300元以内的夹克' → max_price=300，source=rule（场景H）"""
        candidates = extract_entities_with_candidates("推荐300元以内的夹克")
        assert "max_price" in candidates
        assert candidates["max_price"].value == "300"
        assert candidates["max_price"].source == "rule"

    def test_product_id_not_confused_with_price(self):
        """商品ID 29570 不应被识别为价格"""
        candidates = extract_entities_with_candidates("那29570呢？")
        assert "product_id" in candidates
        assert "price" not in candidates
        assert "max_price" not in candidates

    def test_order_id_extraction(self):
        """'查询订单 O20260811000004' → order_id"""
        candidates = extract_entities_with_candidates("查询订单 O20260811000004 的物流")
        assert "order_id" in candidates
        assert candidates["order_id"].value == "O20260811000004"
        assert candidates["order_id"].source == "rule"

    def test_color_and_size_extraction(self):
        """'29570 黑色 M 码' → color + size"""
        candidates = extract_entities_with_candidates("29570 黑色 M 码")
        assert candidates["color"].value == "黑色"
        assert candidates["size"].value == "M"

    def test_backwards_compat_extract_entities(self):
        """旧接口 extract_entities 仍返回 dict[str, Any]（向后兼容）"""
        entities = extract_entities("查询订单 O20260811000004 的物流")
        assert isinstance(entities, dict)
        assert entities["order_id"] == "O20260811000004"


# ──────────────────────────────────────────────────────────────
# J. HybridNLUSettings 自定义阈值
# ──────────────────────────────────────────────────────────────
class TestHybridNLUSettings:

    def test_custom_high_threshold(self):
        """自定义 rule_high_confidence=0.90，0.88 应为 MEDIUM"""
        cfg = HybridNLUSettings(rule_high_confidence=0.90, rule_min_margin=0.10)
        level = evaluate_confidence_level(0.88, 0.25, cfg)
        assert level == ConfidenceLevel.MEDIUM

    def test_default_thresholds(self):
        """默认阈值 0.85 + margin >= 0.20 → HIGH"""
        level = evaluate_confidence_level(0.85, 0.20)
        assert level == ConfidenceLevel.HIGH


# ──────────────────────────────────────────────────────────────
# D. LLM Timeout / Invalid JSON → fail-soft，不 500
# ──────────────────────────────────────────────────────────────
class TestLLMFailSoft:

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_error_result(self):
        """LLM 超时时返回 classifier_error=timeout，不抛异常"""
        from customer_service.intents.structured_llm_classifier import StructuredLLMClassifier

        classifier = StructuredLLMClassifier(enabled=True)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.side_effect = Exception("not supported")

        async def _slow_invoke(*args, **kwargs):
            await asyncio.sleep(10)

        mock_llm.ainvoke = _slow_invoke
        classifier._llm = mock_llm
        classifier._structured_llm = None
        classifier._use_structured_output = False

        result = await classifier.classify(message="测试超时", timeout=0.05)

        assert result.classifier_error == "timeout"
        assert result.is_confident is False

    @pytest.mark.asyncio
    async def test_llm_invalid_json_returns_error(self):
        """LLM 返回非法 JSON → schema_validation_failed 或其他 error，不抛异常"""
        from customer_service.intents.structured_llm_classifier import StructuredLLMClassifier

        classifier = StructuredLLMClassifier(enabled=True)
        mock_llm = MagicMock()
        mock_llm.with_structured_output.side_effect = Exception("not supported")

        async def _bad_invoke(*args, **kwargs):
            resp = MagicMock()
            resp.content = "这根本不是 JSON { broken }"
            return resp

        mock_llm.ainvoke = _bad_invoke
        classifier._llm = mock_llm
        classifier._structured_llm = None
        classifier._use_structured_output = False

        result = await classifier.classify(message="测试", timeout=5.0)

        assert result.classifier_error is not None
        assert result.is_confident is False


# ──────────────────────────────────────────────────────────────
# A（补充）. classify_hybrid 端到端（Rule Only，无需 LLM 网络）
# ──────────────────────────────────────────────────────────────
class TestClassifyHybridRuleOnly:

    @pytest.mark.asyncio
    async def test_logistics_rule_high_skips_llm(self):
        """
        场景A：'查询订单 O20260811000004 的物流' → Rule HIGH
        llm_called=False，意图=logistics_query，order_id=rule 来源
        """
        classifier = IntentClassifier(use_llm=False)
        result = await classifier.classify_hybrid(
            "查询订单 O20260811000004 的物流",
        )
        assert result.llm_called is False
        assert result.rule_intent == BusinessIntent.LOGISTICS_QUERY
        assert "order_id" in result.entities
        assert result.entities["order_id"].source == "rule"

    @pytest.mark.asyncio
    async def test_product_id_entity_from_elliptical_followup(self):
        """
        '那29570呢？' → product_id=29570，source=rule
        """
        classifier = IntentClassifier(use_llm=False)
        result = await classifier.classify_hybrid("那29570呢？")
        assert "product_id" in result.entities
        assert result.entities["product_id"].value == "29570"
        assert result.entities["product_id"].source == "rule"

    @pytest.mark.asyncio
    async def test_result_has_observable_fields(self):
        """
        HybridIntentResult 包含可观测字段（第20节）
        """
        classifier = IntentClassifier(use_llm=False)
        result = await classifier.classify_hybrid("有没有 Puma 的运动鞋？")
        # 可观测字段必须存在
        assert isinstance(result.llm_called, bool)
        assert isinstance(result.source, str)
        assert result.rule_confidence is not None
        assert isinstance(result.entities, dict)
