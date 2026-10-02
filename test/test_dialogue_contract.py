"""
文档第三、四部分验证 - 一轮对话契约

根据文档第189-213行，验证核心契约：
1. 优先级链：取消 → pending_selection → WAITING_SLOT → 常规分类
2. TurnAction 枚举完整性
3. 每个分支都设置 turn_action 和 intent_result
4. 路由函数穷尽检查
5. 闲聊不创建 Task
"""
import pytest
from customer_service.graph.state import AgentState, TaskFrame, TaskStatus
from customer_service.intents.models import BusinessIntent, TurnAction
from customer_service.tasking.models import PendingIntentSelection


class TestTurnActionContract:
    """测试 TurnAction 契约（文档第200-204行）"""

    def test_turn_action_enum_complete(self):
        """TurnAction 应该有文档要求的所有值"""
        # 验证：9种 TurnAction
        assert hasattr(TurnAction, 'ACCEPT')
        assert hasattr(TurnAction, 'CLARIFY')
        assert hasattr(TurnAction, 'SELECT_INTENT')
        assert hasattr(TurnAction, 'CHITCHAT')
        assert hasattr(TurnAction, 'CANCEL')
        assert hasattr(TurnAction, 'RESUME_NOTICE')
        assert hasattr(TurnAction, 'UNSUPPORTED')
        assert hasattr(TurnAction, 'CLASSIFIER_FAILURE')
        assert hasattr(TurnAction, 'OUT_OF_SCOPE')
        
        # 验证：值正确
        assert TurnAction.ACCEPT.value == "accept"
        assert TurnAction.CLARIFY.value == "clarify"
        assert TurnAction.SELECT_INTENT.value == "select_intent"

    def test_turn_initializer_resets_turn_action(self):
        """TurnInitializer 应该每轮重置 turn_action（文档第202行）"""
        from customer_service.graph.turn_initializer import TurnInitializer
        
        # Turn 1: 有 turn_action
        state = AgentState(
            turn_id="turn-1",
            turn_action=TurnAction.ACCEPT
        )
        
        # Turn 2: 初始化
        state = TurnInitializer.initialize_turn(
            state,
            current_message="新消息",
            turn_id="turn-2"
        )
        
        # 验证：turn_action 应该重置为 None
        assert state.get("turn_action") is None


class TestPriorityChain:
    """测试优先级链（文档第189-195行）"""

    @pytest.mark.asyncio
    async def test_cancel_has_highest_priority(self):
        """取消请求应该有最高优先级"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：等待槽位时用户取消
        state = AgentState(
            turn_id="turn-1",
            current_message="取消",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={},
                missing_slots=["keyword"],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            )
        )
        
        result = await intent_parse_node(state, {})
        
        # 验证：应该取消任务
        assert result["turn_action"] == TurnAction.CANCEL
        assert result["active_task"] is None  # 任务已取消

    @pytest.mark.asyncio
    async def test_pending_selection_has_second_priority(self):
        """pending_intent_selection 应该有第二优先级"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：有待选择
        state = AgentState(
            turn_id="turn-2",
            current_message="第一个",
            pending_intent_selection=PendingIntentSelection(
                original_turn_id="turn-1",
                candidate_intents=[
                    BusinessIntent.PRODUCT_QUERY,
                    BusinessIntent.PROMOTION_QUERY
                ]
            )
        )
        
        result = await intent_parse_node(state, {})
        
        # 验证：应该处理选择
        assert result["turn_action"] == TurnAction.ACCEPT
        assert result["pending_intent_selection"] is None

    @pytest.mark.asyncio
    async def test_waiting_slot_has_third_priority(self):
        """WAITING_SLOT 应该有第三优先级"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：等待槽位
        state = AgentState(
            turn_id="turn-3",
            current_message="12345",  # 槽位回答
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PROMOTION_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={},
                missing_slots=["product_id"],
                created_turn_id="turn-2",
                last_turn_id="turn-2"
            )
        )
        
        result = await intent_parse_node(state, {})
        
        # 验证：应该填充槽位
        assert result["turn_action"] == TurnAction.ACCEPT
        assert result["active_task"].slots.get("product_id") == "12345"


class TestChitchatNoTask:
    """测试闲聊不创建Task（文档第221行）"""

    @pytest.mark.asyncio
    async def test_chitchat_does_not_create_task(self):
        """闲聊应该不创建Task"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：首次"你好"
        state = AgentState(
            turn_id="turn-1",
            current_message="你好"
        )
        
        result = await intent_parse_node(state, {})
        
        # 验证：应该是闲聊，不创建任务
        assert result["turn_action"] == TurnAction.CHITCHAT
        assert result.get("active_task") is None  # 没有创建任务

    @pytest.mark.asyncio
    async def test_chitchat_does_not_affect_existing_task(self):
        """闲聊不应该影响现有任务"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：有任务时说"你好"
        state = AgentState(
            turn_id="turn-2",
            current_message="你好",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={},
                missing_slots=["keyword"],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            )
        )
        
        result = await intent_parse_node(state, {})
        
        # 验证：现有任务应该保持不变
        assert result.get("active_task") is not None
        assert result["active_task"].task_id == "task-1"


class TestRoutingContract:
    """测试路由契约（文档第204-207行）"""

    def test_route_after_intent_exhaustive(self):
        """route_after_intent 应该穷尽所有 TurnAction"""
        from customer_service.graph.routing import route_after_intent
        
        # 测试所有已知的 TurnAction
        for action in TurnAction:
            state = AgentState(
                turn_id="test",
                turn_action=action
            )
            
            # 不应该抛出异常
            result = route_after_intent(state)
            assert result in ["check_slots", "respond"]

    def test_route_after_intent_missing_action_raises(self):
        """route_after_intent 缺少 turn_action 应该抛异常"""
        from customer_service.graph.routing import route_after_intent
        
        state = AgentState(
            turn_id="test",
            turn_action=None  # 缺失
        )
        
        # 应该抛出 ValueError
        with pytest.raises(ValueError, match="turn_action 未设置"):
            route_after_intent(state)


class TestUnsupportedIntent:
    """测试未开放意图处理（文档第196行）"""

    @pytest.mark.asyncio
    async def test_unsupported_intent_returns_unsupported_action(self):
        """未开放的意图应该返回 UNSUPPORTED"""
        from customer_service.intents.validator import IntentDecisionValidator
        from customer_service.intents.models import IntentClassificationResult, IntentGoal
        
        validator = IntentDecisionValidator()
        state = AgentState(turn_id="test")
        
        # 识别了物流查询（未开放）
        classification = IntentClassificationResult(
            goals=[
                IntentGoal(
                    intent=BusinessIntent.LOGISTICS_QUERY,
                    confidence=0.9,
                    entities={}
                )
            ],
            is_confident=True,
            is_out_of_scope=False
        )
        
        decision = validator.validate(state, classification)
        
        # 验证：应该返回 UNSUPPORTED
        assert decision.action == TurnAction.UNSUPPORTED
        assert "未开放" in decision.reason  # 简化断言


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
