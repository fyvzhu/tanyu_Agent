"""
测试 SessionUserContext 序列化/反序列化
"""
import sys
import os
import json

# 添加项目路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'customer-service-backend'))

from customer_service.schemas.foundation import SessionUserContext
from pydantic import TypeAdapter


def test_session_user_context_serialization():
    """测试 SessionUserContext 的序列化和反序列化"""
    print("测试 SessionUserContext 序列化...\n")
    
    # 创建实例
    context = SessionUserContext(
        measurement_overrides={"height": 175.0, "weight": 70.0},
        confirmed_measurement_fields=["height", "weight", "bust"]
    )
    
    print(f"原始对象: {context}")
    print(f"  measurement_overrides: {context.measurement_overrides}")
    print(f"  confirmed_measurement_fields: {context.confirmed_measurement_fields}")
    print(f"  confirmed_measurement_fields 类型: {type(context.confirmed_measurement_fields)}")
    
    # 测试 Pydantic 序列化
    try:
        json_dict = context.model_dump()
        print(f"\n✅ model_dump() 成功:")
        print(f"  {json.dumps(json_dict, indent=2, ensure_ascii=False)}")
    except Exception as e:
        print(f"\n❌ model_dump() 失败: {e}")
        return False
    
    # 测试 JSON 序列化
    try:
        json_str = context.model_dump_json()
        print(f"\n✅ model_dump_json() 成功:")
        print(f"  {json_str}")
    except Exception as e:
        print(f"\n❌ model_dump_json() 失败: {e}")
        return False
    
    # 测试反序列化
    try:
        restored = SessionUserContext.model_validate_json(json_str)
        print(f"\n✅ model_validate_json() 成功:")
        print(f"  restored: {restored}")
        print(f"  confirmed_measurement_fields: {restored.confirmed_measurement_fields}")
        print(f"  confirmed_measurement_fields 类型: {type(restored.confirmed_measurement_fields)}")
    except Exception as e:
        print(f"\n❌ model_validate_json() 失败: {e}")
        return False
    
    # 验证数据一致性
    if (context.measurement_overrides == restored.measurement_overrides and
        set(context.confirmed_measurement_fields) == set(restored.confirmed_measurement_fields)):
        print("\n✅ 数据一致性验证通过")
        return True
    else:
        print("\n❌ 数据不一致")
        return False


if __name__ == "__main__":
    result = test_session_user_context_serialization()
    sys.exit(0 if result else 1)
