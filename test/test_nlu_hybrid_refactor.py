"""
NLU Hybrid Refactor - 单元测试

覆盖 NLU_HYBRID_REFACTOR.md 第23节 A-J 测试场景：

A. Rule 高置信度，不调用 LLM
B. Rule 中置信度，LLM 同意
C. Rule 与 LLM 冲突 → CLARIFY
D. LLM Timeout → fail-soft
E. 规则实体不可被 LLM 覆盖
F. Brand 抽取
G. Product Name 抽取
H. Price 抽取
I. 多轮 Context 不被破坏（通过 hybrid_result.intent 继承验证）
J. Slot Check 仍然工作（通过 hybrid_result.entities 验证）

运行：
    cd d:\\tanyu_ecommerce_agent\\customer-service-backend
    C:\\Users\\HP\\anaconda3\\envs\\ECommerce\\python.exe -m pytest ../test/test_nlu_hybrid_refactor.py -v
"""
from __future__ import annotations

import asyncio
import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# 将 customer-service-backend 加入路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "customer-service-backend"))

from customer_service.intents.entity_extractor import (
    extract_entities,
    extract_entities_with_candidates,
)
from customer_service.intents.models import EntityCandidate, HybridIntentResult
from customer_service.intents.hybrid_policy import (
    HybridNLUSettings,
    evaluate_confidence_level,
    should_call_llm,
    fuse_intent,
    ConfidenceLevel,
)
from customer_service.intents.entity_fusion import (
    EntityFusionService,
    rule_entities_to_candidates,
    llm_entities_to_candidates,
)
from customer_service.intents.classifier import IntentClassifier
from customer_service.tasking.models import BusinessIntent


# ===========================================================================
# 测试 A：Rule 高置信度 - 不调用 LLM
# ===========================================================================

def test_rule_high_confidence_policy():
    """Rule HIGH → should_call_llm=False"""
    decision = should_call_llm(
        confidence=0.91,
        margin=0.25,
        ambiguous=False,
        required_entities=[],
        extracted_entities={"order_id": "O20260811000004"},
    )
    assert not decision.should_call, "HIGH confidence 不应调用 LLM"
    assert decision.level == ConfidenceLevel.HIGH


def test_rule_high_entity_complete_no_llm():
    """Rule HIGH + 实体完整 → 不需要 LLM（即使有核心实体要求）"""
    decision = should_call_llm(
        confidence=0.91,
        margin=0.25,
        ambiguous=False,
        required_entities=["brand", "product_name"],
        extracted_entities={
            "brand": MagicMock(value="Puma"),
            "product_name": MagicMock(value="运动鞋"),
        },
    )
    assert not decision.should_call


# ===========================================================================
# 测试 B：Rule 中置信度 → 调用 LLM
# ===========================================================================

def test_rule_medium_confidence_calls_llm():
    """Rule MEDIUM → should_call_llm=True"""
    decision = should_call_llm(
        confidence=0.72,
        margin=0.15,
        ambiguous=False,
        required_entities=[],
        extracted_entities={},
    )
    assert decision.should_call
    assert decision.level == ConfidenceLevel.MEDIUM


# ===========================================================================
# 测试 C：Rule 与 LLM 冲突处理
# ===========================================================================

def test_intent_fusion_conflict_both_high_returns_none():
    """Rule 与 LLM 均 >= 0.80 且意图不同 → CLARIFY（final_intent=None）"""
    final_intent, final_conf, source = fuse_intent(
        rule_intent="product_query",
        rule_confidence=0.83,
        llm_intent="promotion_query",
        llm_confidence=0.91,
        level=ConfidenceLevel.MEDIUM,
    )
    assert final_intent is None, "冲突双高必须 CLARIFY"
    assert source == "rule+llm"


def test_intent_fusion_conflict_llm_wins():
    """LLM >= 0.85 且 Rule < 0.75 → LLM 覆盖规则"""
    final_intent, final_conf, source = fuse_intent(
        rule_intent="product_query",
        rule_confidence=0.69,
        llm_intent="promotion_query",
        llm_confidence=0.90,
        level=ConfidenceLevel.MEDIUM,
    )
    assert final_intent == "promotion_query"
    assert source == "llm"


# ===========================================================================
# 测试 D：LLM Timeout → fail-soft
# ===========================================================================

@pytest.mark.asyncio
async def test_llm_classifier_timeout_returns_error():
    """LLM 超时不能让整个分类失败，应返回 classifier_error='timeout'"""
    from customer_service.intents.structured_llm_classifier import StructuredLLMClassifier

    clf = StructuredLLMClassifier(enabled=True)

    # 模拟 LLM 调用超时
    async def mock_timeout(*args, **kwargs):
        raise asyncio.TimeoutError()

    with patch.object(clf, "_invoke_llm", side_effect=mock_timeout):
        result = await clf.classify("这个有活动吗", timeout=0.001)

    assert result.classifier_error == "timeout"
    assert not result.is_confident
    assert result.goals == []


# ===========================================================================
# 测试 E：规则实体不可被 LLM 覆盖
# ===========================================================================

def test_entity_fusion_rule_cannot_be_overridden_by_llm():
    """product_id 规则实体不能被 LLM 覆盖"""
    rule_entities = rule_entities_to_candidates({"product_id": "29570"})
    llm_entities = llm_entities_to_candidates([
        {"name": "product_id", "value": "15970", "confidence": 0.95}
    ])
    svc = EntityFusionService()
    result = svc.merge(rule_entities, llm_entities)

    assert result["product_id"].value == "29570", "规则 product_id 必须保留，LLM 不能覆盖"
    assert result["product_id"].source == "rule"


def test_entity_fusion_llm_can_add_new_entity():
    """LLM 可以补充规则未提取到的 brand"""
    rule_entities = rule_entities_to_candidates({"product_id": "29570"})
    llm_entities = llm_entities_to_candidates([
        {"name": "brand", "value": "Puma", "confidence": 0.88}
    ])
    svc = EntityFusionService()
    result = svc.merge(rule_entities, llm_entities)

    assert "brand" in result
    assert result["brand"].value == "Puma"
    assert result["brand"].source == "llm"


# ===========================================================================
# 测试 F：Brand 抽取
# ===========================================================================

def test_brand_extraction_puma():
    """输入包含 Puma → brand=Puma"""
    candidates = extract_entities_with_candidates("有没有 Puma 的运动鞋？")
    assert "brand" in candidates
    assert candidates["brand"].value == "Puma"
    assert candidates["brand"].source == "rule"
    assert candidates["brand"].validated is True


def test_brand_extraction_just_natural():
    """输入包含 Just Natural → brand=Just Natural"""
    candidates = extract_entities_with_candidates("Just Natural 中性防雨夹克有活动吗？")
    assert "brand" in candidates
    assert "Just Natural" in candidates["brand"].value


# ===========================================================================
# 测试 G：Product Name 抽取
# ===========================================================================

def test_product_name_extraction():
    """输入包含品类词 → product_name 粗提取"""
    candidates = extract_entities_with_candidates("有没有好看的夹克推荐")
    assert "product_name" in candidates
    assert "夹克" in candidates["product_name"].value
    assert candidates["product_name"].source == "rule"


def test_product_name_not_extracted_when_product_id_present():
    """有精确 product_id 时不提取 product_name"""
    candidates = extract_entities_with_candidates("29570 这件夹克有活动吗")
    # 有 product_id 时不应推断 product_name
    assert "product_id" in candidates
    assert "product_name" not in candidates


# ===========================================================================
# 测试 H：Price 抽取
# ===========================================================================

def test_price_extraction_max_price():
    """预算关键词 → max_price"""
    candidates = extract_entities_with_candidates("推荐300元以内的夹克")
    assert "max_price" in candidates
    assert candidates["max_price"].value == "300"
    assert candidates["max_price"].source == "rule"


def test_price_not_confused_with_product_id():
    """500 元预算不应误识别为 product_id"""
    candidates = extract_entities_with_candidates("我预算500元以内")
    assert "max_price" in candidates
    assert "product_id" not in candidates


# ===========================================================================
# 测试 I：多轮 Context 继承
# ===========================================================================

def test_elliptical_followup_inherits_intent():
    """
    "那29570呢？" 应该继承意图（通过 classify_with_active_intent）
    同时正确提取 product_id=29570
    """
    clf = IntentClassifier()
    result = clf.classify(
        "那29570呢？",
        active_intent=BusinessIntent.PROMOTION_QUERY
    )
    # 省略式追问应继承 PROMOTION_QUERY
    assert result.intent == BusinessIntent.PROMOTION_QUERY
    assert result.inherited is True
    # 实体中应包含 product_id
    assert "product_id" in result.entities
    assert result.entities["product_id"] == "29570"


# ===========================================================================
# 测试 J：Slot Check 验证（间接验证实体输出格式）
# ===========================================================================

def test_entity_candidate_structure():
    """entity_extractor 输出应包含 source/confidence 字段"""
    candidates = extract_entities_with_candidates("查询订单 O20260811000004 的物流")
    assert "order_id" in candidates
    ec = candidates["order_id"]
    assert isinstance(ec, EntityCandidate)
    assert ec.source == "rule"
    assert ec.confidence > 0.9
    assert ec.value == "O20260811000004"


def test_hybrid_intent_result_to_entities_dict():
    """HybridIntentResult.to_entities_dict() 应返回 dict[str, Any]（兼容旧代码）"""
    from customer_service.intents.models import HybridIntentResult
    ec = EntityCandidate(name="color", value="黑色", source="rule", confidence=0.88)
    h = HybridIntentResult(
        intent=BusinessIntent.PRODUCT_QUERY,
        confidence=0.90,
        source="rule",
        entities={"color": ec},
    )
    d = h.to_entities_dict()
    assert d["color"] == "黑色"
    assert isinstance(d, dict)


# ===========================================================================
# 运行
# ===========================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
