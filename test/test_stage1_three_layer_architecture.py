"""
阶段1测试：三层架构（分类器→验证器→决策）

测试验证器的核心规则：
1. 多目标冲突检测（MULTIPLE_TRACKS）
2. 能力开放检查（白名单）
3. 闲聊不启动任务
4. 低置信度拒绝
5. 分类器失败处理
"""
import sys
import os

# 设置路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "customer-service-backend"))

import pytest
from customer_service.intents.models import (
    IntentClassificationResult,
    IntentGoal,
    TurnAction,
    BusinessIntent,
)
from customer_service.intents.validator import IntentDecisionValidator
from customer_service.graph.state import AgentState


def test_validator_rejects_multiple_goals():
    """测试：多目标冲突检测"""
    validator = IntentDecisionValidator()
    
    # 构造两个业务目标
    classification = IntentClassificationResult(
        goals=[
            IntentGoal(intent=BusinessIntent.PRODUCT_QUERY, entities={}, confidence=0.8),
            IntentGoal(intent=BusinessIntent.PROMOTION_QUERY, entities={}, confidence=0.7),
        ],
        is_confident=True,
        is_out_of_scope=False,
    )
    
    state: AgentState = {"turn_id": "test_001"}
    decision = validator.validate(state, classification)
    
    # 应该返回 SELECT_INTENT（需要用户选择）
    assert decision.action == TurnAction.SELECT_INTENT
    assert decision.clarify_options is not None
    assert len(decision.clarify_options) == 2
    print("✅ 多目标冲突检测通过")


def test_validator_rejects_unsupported_intent():
    """测试：能力开放检查 - 拒绝未开放的意图"""
    validator = IntentDecisionValidator()
    
    # RETURN 和 EXCHANGE 当前未开放
    classification = IntentClassificationResult(
        goals=[
            IntentGoal(intent=BusinessIntent.RETURN, entities={}, confidence=0.9),
        ],
        is_confident=True,
        is_out_of_scope=False,
    )
    
    state: AgentState = {"turn_id": "test_002"}
    decision = validator.validate(state, classification)
    
    # 应该返回 UNSUPPORTED
    assert decision.action == TurnAction.UNSUPPORTED
    assert "未开放" in decision.reason
    print("✅ 能力开放检查通过")


def test_validator_accepts_chitchat():
    """测试：闲聊不启动任务"""
    validator = IntentDecisionValidator()
    
    classification = IntentClassificationResult(
        goals=[
            IntentGoal(intent=BusinessIntent.CHITCHAT, entities={}, confidence=0.9),
        ],
        is_confident=True,
        is_out_of_scope=False,
    )
    
    state: AgentState = {"turn_id": "test_003"}
    decision = validator.validate(state, classification)
    
    # 应该返回 CHITCHAT（不是 ACCEPT）
    assert decision.action == TurnAction.CHITCHAT
    assert decision.accepted_goal is not None
    assert decision.accepted_goal.intent == BusinessIntent.CHITCHAT
    print("✅ 闲聊处理通过")


def test_validator_rejects_low_confidence():
    """测试：低置信度拒绝"""
    validator = IntentDecisionValidator()
    
    classification = IntentClassificationResult(
        goals=[
            IntentGoal(intent=BusinessIntent.PRODUCT_QUERY, entities={}, confidence=0.4),
        ],
        is_confident=False,  # 关键：标记为低置信度
        is_out_of_scope=False,
    )
    
    state: AgentState = {"turn_id": "test_004"}
    decision = validator.validate(state, classification)
    
    # 应该返回 CLARIFY
    assert decision.action == TurnAction.CLARIFY
    assert "置信度" in decision.reason
    print("✅ 低置信度拒绝通过")


def test_validator_handles_classifier_failure():
    """测试：分类器失败处理"""
    validator = IntentDecisionValidator()
    
    classification = IntentClassificationResult(
        goals=[],
        is_confident=False,
        is_out_of_scope=False,
        classifier_error="LLM timeout",
    )
    
    state: AgentState = {"turn_id": "test_005"}
    decision = validator.validate(state, classification)
    
    # 应该返回 CLASSIFIER_FAILURE
    assert decision.action == TurnAction.CLASSIFIER_FAILURE
    assert "分类器错误" in decision.reason
    print("✅ 分类器失败处理通过")


def test_validator_accepts_supported_intent():
    """测试：接受支持的意图"""
    validator = IntentDecisionValidator()
    
    # PRODUCT_QUERY 是开放的
    classification = IntentClassificationResult(
        goals=[
            IntentGoal(
                intent=BusinessIntent.PRODUCT_QUERY, 
                entities={"color": "红色"}, 
                confidence=0.9
            ),
        ],
        is_confident=True,
        is_out_of_scope=False,
    )
    
    state: AgentState = {"turn_id": "test_006"}
    decision = validator.validate(state, classification)
    
    # 应该返回 ACCEPT
    assert decision.action == TurnAction.ACCEPT
    assert decision.accepted_goal is not None
    assert decision.accepted_goal.intent == BusinessIntent.PRODUCT_QUERY
    assert decision.accepted_goal.entities.get("color") == "红色"
    print("✅ 接受支持的意图通过")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
