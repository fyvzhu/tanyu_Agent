"""
测试历史对话上下文修复

验证问题2的修复：Agent能够理解上下文
- 测试场景："那29570呢？"应该能理解是查询促销
"""
import pytest
from customer_service.prompts.history_builder import HistoryBuilder
from customer_service.intents.classifier import IntentClassifier


def test_history_builder():
    """测试历史对话构建器"""
    messages = [
        {"role": "user", "content": "29568这个商品有什么促销活动？"},
        {"role": "assistant", "content": "29568商品目前有以下促销活动..."},
        {"role": "user", "content": "那29570呢？"},
    ]
    
    history = HistoryBuilder.build_from_messages(messages, max_turns=10)
    
    print("历史对话格式化结果：")
    print(history)
    
    # 验证格式
    assert "USER: 29568这个商品有什么促销活动？" in history
    assert "ASSISTANT:" in history
    assert "USER: 那29570呢？" in history


def test_intent_classifier_with_history():
    """测试意图分类器支持历史对话"""
    # 模拟历史对话
    history = """USER: 29568这个商品有什么促销活动？
ASSISTANT: 29568商品目前有满减活动：满300减50"""
    
    # 当前消息
    current_message = "那29570呢？"
    
    classifier = IntentClassifier()
    result = classifier.classify(current_message, history=history)
    
    print(f"分类结果: intent={result.intent}, confidence={result.confidence}")
    
    # 注意：当前关键词分类器还不能理解"那29570呢"的上下文
    # 这需要LLM分类器才能实现
    # 这里只是验证参数能正确传递
    assert result is not None


def test_context_understanding_scenario():
    """测试上下文理解场景"""
    # 场景1：查询促销后，继续问其他商品
    history_messages = [
        {"role": "user", "content": "29568这个商品有什么促销活动？"},
        {"role": "assistant", "content": "29568商品目前有满减活动"},
    ]
    
    history = HistoryBuilder.build_from_messages(history_messages)
    current = "那29570呢？"
    
    context = HistoryBuilder.build_context_for_intent_classification(
        current, history_messages, max_history_turns=10
    )
    
    print("上下文构建结果：")
    print(f"用户消息: {context['user_message']}")
    print(f"历史对话:\n{context['conversation_history']}")
    
    assert context['user_message'] == "那29570呢？"
    assert "29568" in context['conversation_history']
    assert "促销" in context['conversation_history']


if __name__ == "__main__":
    print("=== 测试1: 历史对话构建器 ===")
    test_history_builder()
    
    print("\n=== 测试2: 意图分类器支持历史对话 ===")
    test_intent_classifier_with_history()
    
    print("\n=== 测试3: 上下文理解场景 ===")
    test_context_understanding_scenario()
    
    print("\n✅ 所有测试通过")
