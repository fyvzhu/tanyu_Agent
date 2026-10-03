"""
P2修复验证：Context Resolver上下文解析

测试Context Resolver能否正确处理省略式追问、指代消解、补槽等场景

运行方式：
cd customer-service-backend
python -m pytest ../test/test_context_resolver.py -v -s
"""
import pytest
from customer_service.graph.context_resolver import ContextResolver, ContextResolution
from customer_service.graph.dialogue_frame import DialogueFrame, FocusRef
from customer_service.tasking.models import BusinessIntent, TaskFrame, TaskStatus


def test_context_resolver_elliptical_followup():
    """测试省略式追问解析"""
    resolver = ContextResolver()
    
    # 场景：上一轮promotion_query，这一轮"那29570呢？"
    dialogue_frame = DialogueFrame(
        last_business_intent=BusinessIntent.PROMOTION_QUERY,
        last_focus=FocusRef(entity_type="product", entity_id="29568"),
        last_slots={"product_id": "29568"}
    )
    
    resolution = resolver.resolve(
        current_message="那29570呢？",
        dialogue_frame=dialogue_frame,
        active_task=None,
        turn_id="test_001"
    )
    
    # 验证
    assert resolution.mode == "repeat_last_intent"
    assert resolution.inherited_intent == BusinessIntent.PROMOTION_QUERY
    assert resolution.entity_updates.get("product_id") == "29570"
    assert resolution.confidence == 1.0
    
    print(f"✅ 省略式追问: {resolution.reasoning}")


def test_context_resolver_referential_expression():
    """测试指代表达解析"""
    resolver = ContextResolver()
    
    # 场景：上一轮查询了商品29568，这一轮"这个怎么样？"
    dialogue_frame = DialogueFrame(
        last_business_intent=BusinessIntent.PRODUCT_QUERY,
        last_focus=FocusRef(entity_type="product", entity_id="29568", entity_name="男士衬衫"),
        last_slots={"product_id": "29568"}
    )
    
    resolution = resolver.resolve(
        current_message="这个怎么样？",
        dialogue_frame=dialogue_frame,
        active_task=None,
        turn_id="test_002"
    )
    
    # 验证
    assert resolution.mode == "repeat_last_intent"
    assert resolution.inherited_intent == BusinessIntent.PRODUCT_QUERY
    assert resolution.entity_updates.get("product_id") == "29568"
    assert resolution.confidence == 0.9  # 指代消解置信度略低
    
    print(f"✅ 指代表达: {resolution.reasoning}")


def test_context_resolver_slot_filling():
    """测试补槽场景"""
    resolver = ContextResolver()
    
    # 场景：active_task缺少product_id槽位，用户回复"29570"
    active_task = TaskFrame(
        task_id="task_001",
        intent=BusinessIntent.PROMOTION_QUERY,
        status=TaskStatus.ACTIVE,
        created_turn_id="turn_001",
        last_turn_id="turn_001",
        slots={"missing_slots": ["product_id"]}
    )
    
    resolution = resolver.resolve(
        current_message="29570",
        dialogue_frame=None,
        active_task=active_task,
        turn_id="test_003"
    )
    
    # 验证
    assert resolution.mode == "continue_active_task"
    assert resolution.entity_updates.get("product_id") == "29570"
    assert resolution.confidence == 1.0
    
    print(f"✅ 补槽场景: {resolution.reasoning}")


def test_context_resolver_new_explicit_goal():
    """测试显式新目标"""
    resolver = ContextResolver()
    
    # 场景：用户发起新的完整请求
    resolution = resolver.resolve(
        current_message="我要查询订单物流",
        dialogue_frame=None,
        active_task=None,
        turn_id="test_004"
    )
    
    # 验证
    assert resolution.mode == "new_explicit_goal"
    assert resolution.inherited_intent is None
    assert resolution.confidence == 1.0
    
    print(f"✅ 显式新目标: {resolution.reasoning}")


def test_context_resolver_multiple_entities():
    """测试多实体更新"""
    resolver = ContextResolver()
    
    # 场景：省略式追问 + 多个实体
    dialogue_frame = DialogueFrame(
        last_business_intent=BusinessIntent.PRODUCT_QUERY,
        last_slots={"category": "男士衬衫"}
    )
    
    resolution = resolver.resolve(
        current_message="那黑色L码呢？",
        dialogue_frame=dialogue_frame,
        active_task=None,
        turn_id="test_005"
    )
    
    # 验证
    assert resolution.mode == "repeat_last_intent"
    assert resolution.inherited_intent == BusinessIntent.PRODUCT_QUERY
    # 应该提取到颜色和尺码
    assert "color" in resolution.entity_updates or "size" in resolution.entity_updates
    
    print(f"✅ 多实体更新: entities={resolution.entity_updates}")


def test_context_resolver_no_dialogue_frame():
    """测试无DialogueFrame时的省略式追问"""
    resolver = ContextResolver()
    
    # 场景：没有dialogue_frame，但有active_task
    active_task = TaskFrame(
        task_id="task_001",
        intent=BusinessIntent.SIZE_RECOMMEND,
        status=TaskStatus.ACTIVE,
        created_turn_id="turn_001",
        last_turn_id="turn_001",
        slots={"product_id": "29568"}
    )
    
    resolution = resolver.resolve(
        current_message="那29570呢？",
        dialogue_frame=None,
        active_task=active_task,
        turn_id="test_006"
    )
    
    # 验证：应该从active_task继承意图
    assert resolution.mode == "repeat_last_intent"
    assert resolution.inherited_intent == BusinessIntent.SIZE_RECOMMEND
    assert resolution.entity_updates.get("product_id") == "29570"
    
    print(f"✅ 无DialogueFrame但有active_task: {resolution.reasoning}")


if __name__ == "__main__":
    print("=" * 60)
    print("P2修复验证：Context Resolver上下文解析")
    print("=" * 60)
    
    test_context_resolver_elliptical_followup()
    print()
    test_context_resolver_referential_expression()
    print()
    test_context_resolver_slot_filling()
    print()
    test_context_resolver_new_explicit_goal()
    print()
    test_context_resolver_multiple_entities()
    print()
    test_context_resolver_no_dialogue_frame()
    
    print("\n" + "=" * 60)
    print("✅ 所有测试通过！")
    print("=" * 60)
