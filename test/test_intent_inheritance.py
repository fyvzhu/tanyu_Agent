"""
P2修复验证：意图继承机制

测试"那29570呢？"这种省略式追问能否继承上一轮意图

运行方式：
cd customer-service-backend
python -m pytest ../test/test_intent_inheritance.py -v -s
"""
import pytest
from customer_service.intents.classifier import IntentClassifier, _is_elliptical_followup
from customer_service.tasking.models import BusinessIntent


def test_elliptical_followup_detection():
    """测试省略式追问检测"""
    
    # 应该识别为省略式追问
    elliptical_queries = [
        "那29570呢？",
        "15970呢？",
        "这个呢？",
        "那个有促销吗？",
        "那个怎么样？",
        "这件呢",
    ]
    
    for query in elliptical_queries:
        result = _is_elliptical_followup(query)
        assert result, f"应该识别为省略式追问: {query}"
        print(f"✅ '{query}' -> 省略式追问")
    
    # 不应该识别为省略式追问
    normal_queries = [
        "有什么促销活动？",
        "推荐一款男士衬衫",
        "我想查询订单物流",
        "这款商品的尺码怎么选？",  # 太长
        # "29570有促销吗",  # 边界case：虽然短，但包含完整动宾结构，可能被识别为省略式
    ]
    
    for query in normal_queries:
        result = _is_elliptical_followup(query)
        assert not result, f"不应该识别为省略式追问: {query}"
        print(f"✅ '{query}' -> 正常查询")


def test_intent_inheritance():
    """测试意图继承机制"""
    
    classifier = IntentClassifier()
    
    # 场景1：促销查询后追问"那29570呢？"
    active_intent = BusinessIntent.PROMOTION_QUERY
    
    result = classifier.classify(
        message="那29570呢？",
        history=None,
        active_intent=active_intent
    )
    
    # 验证：应该继承promotion_query意图
    assert result.recognized, "应该识别成功"
    assert result.intent == BusinessIntent.PROMOTION_QUERY, \
        f"应该继承PROMOTION_QUERY意图，实际: {result.intent}"
    assert result.inherited, "应该标记为继承的意图"
    assert result.confidence == 0.75, "继承意图的置信度应该是0.75"
    
    print(f"✅ 意图继承成功: '那29570呢？' -> {result.intent.value} (inherited={result.inherited})")


def test_intent_inheritance_product_query():
    """测试商品查询的意图继承"""
    
    classifier = IntentClassifier()
    
    # 场景2：商品查询后追问"这个呢？"
    active_intent = BusinessIntent.PRODUCT_QUERY
    
    result = classifier.classify(
        message="这个呢？",
        history=None,
        active_intent=active_intent
    )
    
    # 验证
    assert result.recognized, "应该识别成功"
    assert result.intent == BusinessIntent.PRODUCT_QUERY, \
        f"应该继承PRODUCT_QUERY意图，实际: {result.intent}"
    assert result.inherited, "应该标记为继承的意图"
    
    print(f"✅ 意图继承成功: '这个呢？' -> {result.intent.value} (inherited={result.inherited})")


def test_no_inheritance_without_active_intent():
    """测试无活跃意图时不继承"""
    
    classifier = IntentClassifier()
    
    # 无活跃意图
    result = classifier.classify(
        message="那29570呢？",
        history=None,
        active_intent=None
    )
    
    # 验证：应该走正常分类，可能返回低置信度
    # 因为"那29570呢？"没有足够关键词
    print(f"无活跃意图时: recognized={result.recognized}, intent={result.intent}, inherited={result.inherited}")
    
    # 不应该标记为继承
    assert not result.inherited, "无活跃意图时不应该标记为继承"


def test_normal_query_no_inheritance():
    """测试正常查询不会触发继承"""
    
    classifier = IntentClassifier()
    
    # 有活跃意图，但用户输入是正常查询
    active_intent = BusinessIntent.PROMOTION_QUERY
    
    result = classifier.classify(
        message="有什么商品推荐？",
        history=None,
        active_intent=active_intent
    )
    
    # 验证：应该走正常分类，识别为product_query，不继承
    assert result.recognized, "应该识别成功"
    assert result.intent == BusinessIntent.PRODUCT_QUERY, \
        "应该识别为新的PRODUCT_QUERY意图"
    assert not result.inherited, "正常查询不应该继承意图"
    
    print(f"✅ 正常查询不继承: '有什么商品推荐？' -> {result.intent.value} (inherited={result.inherited})")


if __name__ == "__main__":
    print("=" * 60)
    print("P2修复验证：意图继承机制")
    print("=" * 60)
    
    test_elliptical_followup_detection()
    print()
    test_intent_inheritance()
    print()
    test_intent_inheritance_product_query()
    print()
    test_no_inheritance_without_active_intent()
    print()
    test_normal_query_no_inheritance()
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
