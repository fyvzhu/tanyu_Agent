"""
P2修复验证：DialogueFrame和商品ID提取

测试DialogueFrame能否正确保存和恢复对话语义上下文

运行方式：
cd customer-service-backend
python -m pytest ../test/test_dialogue_frame.py -v -s
"""
import pytest
from customer_service.graph.dialogue_frame import DialogueFrame, FocusRef
from customer_service.tasking.models import BusinessIntent, TaskFrame, TaskStatus
from customer_service.intents.entity_extractor import extract_entities


def test_dialogue_frame_initialization():
    """测试DialogueFrame初始化"""
    frame = DialogueFrame()
    
    assert frame.last_business_intent is None
    assert frame.last_focus is None
    assert frame.last_slots == {}
    assert frame.last_completed_task_id is None
    assert frame.last_updated_turn_id is None
    
    print("✅ DialogueFrame初始化正确")


def test_dialogue_frame_update_from_task():
    """测试从Task更新DialogueFrame"""
    frame = DialogueFrame()

    # 创建一个促销查询任务
    task = TaskFrame(
        task_id="task_001",
        intent=BusinessIntent.PROMOTION_QUERY,
        status=TaskStatus.ACTIVE,
        created_turn_id="turn_001",
        last_turn_id="turn_001",
        slots={
            "product_id": "29568",
            "product_name": "男士衬衫",
            "category": "服装"
        }
    )
    
    # 更新DialogueFrame
    frame.update_from_task(task, turn_id="turn_001")
    
    # 验证
    assert frame.last_business_intent == BusinessIntent.PROMOTION_QUERY
    assert frame.last_focus is not None
    assert frame.last_focus.entity_type == "product"
    assert frame.last_focus.entity_id == "29568"
    assert frame.last_focus.entity_name == "男士衬衫"
    assert frame.last_slots["product_id"] == "29568"
    assert frame.last_updated_turn_id == "turn_001"
    
    print(f"✅ DialogueFrame更新成功: {frame.get_context_summary()}")


def test_dialogue_frame_serialization():
    """测试DialogueFrame序列化和反序列化"""
    frame = DialogueFrame(
        last_business_intent=BusinessIntent.PROMOTION_QUERY,
        last_focus=FocusRef(
            entity_type="product",
            entity_id="29568",
            entity_name="男士衬衫"
        ),
        last_slots={"product_id": "29568", "category": "服装"},
        last_completed_task_id="task_001",
        last_updated_turn_id="turn_001"
    )
    
    # 序列化
    data = frame.to_dict()
    
    # 反序列化
    restored_frame = DialogueFrame.from_dict(data)
    
    # 验证
    assert restored_frame.last_business_intent == BusinessIntent.PROMOTION_QUERY
    assert restored_frame.last_focus.entity_id == "29568"
    assert restored_frame.last_slots["product_id"] == "29568"
    assert restored_frame.last_completed_task_id == "task_001"
    
    print("✅ DialogueFrame序列化/反序列化成功")


def test_product_id_extraction_elliptical():
    """测试省略式追问中的商品ID提取"""
    
    test_cases = [
        ("那29570呢？", "29570"),
        ("15970呢？", "15970"),
        ("那29570有什么促销吗？", "29570"),
        ("这个29568怎么样？", "29568"),
    ]
    
    for message, expected_id in test_cases:
        entities = extract_entities(message)
        actual_id = entities.get("product_id")
        
        assert actual_id == expected_id, \
            f"消息'{message}'应该提取product_id={expected_id}，实际={actual_id}"
        
        print(f"✅ '{message}' -> product_id={actual_id}")


def test_product_id_extraction_with_context():
    """测试有上下文关键词的商品ID提取"""
    
    # 有促销相关关键词
    message = "29570有优惠吗"
    entities = extract_entities(message)
    assert entities.get("product_id") == "29570"
    print(f"✅ '{message}' -> product_id={entities['product_id']}")
    
    # 有推荐关键词
    message = "推荐29570"
    entities = extract_entities(message)
    assert entities.get("product_id") == "29570"
    print(f"✅ '{message}' -> product_id={entities['product_id']}")


def test_dialogue_frame_context_summary():
    """测试DialogueFrame上下文摘要"""
    
    # 空上下文
    frame = DialogueFrame()
    assert frame.get_context_summary() == "无上下文"
    
    # 有意图和焦点
    frame = DialogueFrame(
        last_business_intent=BusinessIntent.PROMOTION_QUERY,
        last_focus=FocusRef(entity_type="product", entity_id="29568"),
        last_slots={"product_id": "29568", "category": "服装"}
    )
    
    summary = frame.get_context_summary()
    assert "promotion_query" in summary
    assert "product:29568" in summary
    assert "槽位" in summary
    
    print(f"✅ 上下文摘要: {summary}")


if __name__ == "__main__":
    print("=" * 60)
    print("P2修复验证：DialogueFrame和商品ID提取")
    print("=" * 60)
    
    test_dialogue_frame_initialization()
    print()
    test_dialogue_frame_update_from_task()
    print()
    test_dialogue_frame_serialization()
    print()
    test_product_id_extraction_elliptical()
    print()
    test_product_id_extraction_with_context()
    print()
    test_dialogue_frame_context_summary()
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
