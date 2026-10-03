"""
测试DialogueFrame反序列化问题

模拟从Redis恢复后的场景
"""
import sys
sys.path.insert(0, "customer-service-backend")

from customer_service.graph.dialogue_frame import DialogueFrame, FocusRef
from customer_service.graph.task_context_manager import _ensure_dialogue_frame
from customer_service.tasking.models import BusinessIntent

# 模拟LangChain序列化后的格式（包括嵌套的FocusRef）
serialized_frame = {
    'lc': 2,
    'type': 'constructor',
    'id': ['customer_service', 'graph', 'dialogue_frame', 'DialogueFrame'],
    'kwargs': {
        'last_business_intent': 'promotion_query',
        'last_focus': {
            'lc': 2,
            'type': 'constructor',
            'id': ['customer_service', 'graph', 'dialogue_frame', 'FocusRef'],
            'kwargs': {
                'entity_type': 'product',
                'entity_id': '29568',
                'entity_name': None
            }
        },
        'last_slots': {'product_id': '29568'},
        'last_completed_task_id': 'some-task-id',
        'last_updated_turn_id': 'some-turn-id'
    }
}

print("=" * 60)
print("测试1: 处理LangChain序列化格式")
print("=" * 60)

state = {"dialogue_frame": serialized_frame}
print(f"处理前类型: {type(state['dialogue_frame'])}")
print(f"处理前内容: {state['dialogue_frame']}")

result = _ensure_dialogue_frame(state)
print(f"\n处理后类型: {type(result)}")
print(f"处理后内容: {result}")

if result:
    print(f"\nlast_business_intent: {result.last_business_intent}")
    print(f"last_focus: {result.last_focus}")
    print(f"可以调用方法: {result.get_context_summary()}")
    print("\n✅ 测试1通过!")
else:
    print("\n❌ 测试1失败!")

print("\n" + "=" * 60)
print("测试2: 处理普通dict格式")
print("=" * 60)

plain_dict = {
    'last_business_intent': BusinessIntent.PROMOTION_QUERY,
    'last_focus': FocusRef(entity_type='product', entity_id='29570'),
    'last_slots': {},
    'last_completed_task_id': None,
    'last_updated_turn_id': None
}

state2 = {"dialogue_frame": plain_dict}
print(f"处理前类型: {type(state2['dialogue_frame'])}")

result2 = _ensure_dialogue_frame(state2)
print(f"处理后类型: {type(result2)}")

if result2:
    print(f"可以访问属性: {result2.last_business_intent}")
    print("\n✅ 测试2通过!")
else:
    print("\n❌ 测试2失败!")

print("\n" + "=" * 60)
print("测试3: 已经是对象的情况")
print("=" * 60)

obj = DialogueFrame()
state3 = {"dialogue_frame": obj}
result3 = _ensure_dialogue_frame(state3)

if result3 is obj:
    print("✅ 测试3通过! (返回同一对象)")
else:
    print("❌ 测试3失败!")

print("\n" + "=" * 60)
print("所有测试完成")
print("=" * 60)
