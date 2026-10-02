"""
阶段4测试：client_context 验证与对象点击

测试目标：
1. client_context 只接受 type 和 id
2. 不信任客户端提供的价格、库存等
3. ID 格式校验（商品4-6位，订单8位以上）
4. 验证后的对象可用于槽位补填

对应文档：
- 第83-88行：P1问题描述
- "必须区分'点击指定对象'和'浏览器提供业务事实'"
"""
import pytest
from customer_service.graph.turn_initializer import TurnInitializer
from customer_service.graph.state import AgentState


class TestClientContextValidation:
    """测试 client_context 验证"""

    def test_valid_product_context(self):
        """有效的商品点击"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="这款有优惠吗",
            turn_id="test-1",
            client_context={"type": "product", "id": "15970"}
        )
        
        assert result["verified_object_id"] is not None
        assert result["verified_object_id"]["type"] == "product"
        assert result["verified_object_id"]["id"] == "15970"

    def test_valid_order_context(self):
        """有效的订单点击"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查物流",
            turn_id="test-2",
            client_context={"type": "order", "id": "12345678"}
        )
        
        assert result["verified_object_id"] is not None
        assert result["verified_object_id"]["type"] == "order"
        assert result["verified_object_id"]["id"] == "12345678"

    def test_reject_fake_price(self):
        """拒绝客户端提供的假价格"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="这款多少钱",
            turn_id="test-3",
            client_context={
                "type": "product",
                "id": "15970",
                "price": 1,  # 假价格
                "stock": 999,  # 假库存
            }
        )
        
        # 应该通过验证，但忽略价格和库存
        assert result["verified_object_id"] is not None
        assert result["verified_object_id"] == {"type": "product", "id": "15970"}
        # 不应该包含价格和库存
        assert "price" not in result["verified_object_id"]
        assert "stock" not in result["verified_object_id"]

    def test_reject_invalid_product_id_too_short(self):
        """拒绝过短的商品ID（<4位）"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查询",
            turn_id="test-4",
            client_context={"type": "product", "id": "123"}  # 只有3位
        )
        
        assert result["verified_object_id"] is None

    def test_reject_invalid_product_id_too_long(self):
        """拒绝过长的商品ID（>6位）"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查询",
            turn_id="test-5",
            client_context={"type": "product", "id": "1234567"}  # 7位
        )
        
        assert result["verified_object_id"] is None

    def test_reject_invalid_order_id_too_short(self):
        """拒绝过短的订单ID（<8位）"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查物流",
            turn_id="test-6",
            client_context={"type": "order", "id": "1234567"}  # 只有7位
        )
        
        assert result["verified_object_id"] is None

    def test_reject_non_numeric_id(self):
        """拒绝非数字ID"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查询",
            turn_id="test-7",
            client_context={"type": "product", "id": "abc123"}
        )
        
        assert result["verified_object_id"] is None

    def test_reject_missing_type(self):
        """拒绝缺少 type"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查询",
            turn_id="test-8",
            client_context={"id": "15970"}  # 缺少 type
        )
        
        assert result["verified_object_id"] is None

    def test_reject_missing_id(self):
        """拒绝缺少 id"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="查询",
            turn_id="test-9",
            client_context={"type": "product"}  # 缺少 id
        )
        
        assert result["verified_object_id"] is None

    def test_no_client_context(self):
        """没有 client_context（正常文本消息）"""
        state = AgentState(turn_id="test-0")
        
        result = TurnInitializer.initialize_turn(
            state=state,
            current_message="推荐跑鞋",
            turn_id="test-10",
            client_context=None
        )
        
        assert result["verified_object_id"] is None
        assert result["current_message"] == "推荐跑鞋"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
