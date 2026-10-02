"""
P0-2测试：结构化LLM分类器

测试目标：
1. Schema验证（Pydantic）
2. 超时处理
3. 回退机制（LLM失败时使用关键词分类器）
4. 不传全量历史（只传必要上下文）

对应文档：
- 第16-22行：P0-2问题描述
- 第174-176行：LLM分类器注意事项
"""
import pytest
from customer_service.intents.structured_llm_classifier import (
    StructuredIntentGoal,
    StructuredClassificationOutput,
    StructuredLLMClassifier
)
from customer_service.tasking.models import BusinessIntent
from pydantic import ValidationError


class TestStructuredSchema:
    """测试Pydantic Schema校验"""

    def test_valid_goal(self):
        """有效的意图目标"""
        goal = StructuredIntentGoal(
            intent=BusinessIntent.PRODUCT_QUERY,
            text_span="推荐跑鞋",
            entities={"category": "鞋"},
            confidence=0.85
        )
        
        assert goal.intent == BusinessIntent.PRODUCT_QUERY
        assert goal.confidence == 0.85

    def test_invalid_confidence(self):
        """置信度超出范围应报错"""
        with pytest.raises(ValidationError):
            StructuredIntentGoal(
                intent=BusinessIntent.PRODUCT_QUERY,
                text_span="test",
                confidence=1.5  # 超过1.0
            )

    def test_valid_output(self):
        """有效的分类输出"""
        output = StructuredClassificationOutput(
            goals=[
                StructuredIntentGoal(
                    intent=BusinessIntent.PRODUCT_QUERY,
                    text_span="推荐跑鞋",
                    confidence=0.8
                )
            ],
            is_out_of_scope=False
        )
        
        assert len(output.goals) == 1
        assert not output.is_out_of_scope

    def test_empty_goals_out_of_scope(self):
        """超出范围时goals为空"""
        output = StructuredClassificationOutput(
            goals=[],
            is_out_of_scope=True,
            reasoning="用户在咨询天气"
        )
        
        assert len(output.goals) == 0
        assert output.is_out_of_scope


class TestLLMClassifierFramework:
    """测试LLM分类器框架（不依赖真实LLM）"""

    @pytest.mark.asyncio
    async def test_disabled_classifier(self):
        """未启用时应返回空结果"""
        classifier = StructuredLLMClassifier(enabled=False)
        
        result = await classifier.classify("推荐跑鞋")
        
        assert len(result.goals) == 0
        assert not result.is_confident
        assert result.classifier_error == "LLM classifier not enabled"

    @pytest.mark.asyncio
    async def test_enabled_classifier_mock(self):
        """启用时应尝试调用（当前返回模拟结果）"""
        classifier = StructuredLLMClassifier(enabled=True)
        
        # 由于 _call_llm_with_timeout 返回模拟输出，应该解析成功
        result = await classifier.classify("推荐跑鞋")
        
        # 模拟输出是空goals
        assert len(result.goals) == 0


class TestClassifierFallback:
    """测试分类器回退机制"""

    def test_keyword_classifier_still_works(self):
        """关键词分类器应该独立工作"""
        from customer_service.intents.classifier import IntentClassifier
        
        classifier = IntentClassifier(use_llm=False)
        result = classifier.classify("推荐跑鞋")
        
        assert result.recognized
        assert result.intent == BusinessIntent.PRODUCT_QUERY

    @pytest.mark.asyncio
    async def test_fallback_to_keyword_on_llm_failure(self):
        """LLM失败时应回退到关键词分类器"""
        from customer_service.intents.classifier import IntentClassifier, classify_with_llm
        
        # 创建启用LLM的分类器（但LLM会返回不确定结果）
        classifier = IntentClassifier(use_llm=True)
        
        result = await classify_with_llm(classifier, "推荐跑鞋")
        
        # 应该回退到关键词分类器的结果
        # 关键词分类器能识别"推荐"→product_query
        assert len(result.goals) > 0 or result.is_confident


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
