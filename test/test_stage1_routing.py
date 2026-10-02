"""
阶段1测试：图契约贯通 - 路由逻辑测试

测试目标：
1. 验证 turn_action 设置后路由是否正确
2. 验证 guard_status 设置后路由是否正确
3. 验证未知状态是否抛出错误
4. 验证节点访问序列是否符合预期

不涉及：
- 分类器算法（留到阶段2）
- 任务栈管理（留到阶段2）
- 实际Flow执行（使用假Flow）
"""
import pytest
from customer_service.intents.models import TurnAction, GuardStatus, IntentDecision, BusinessIntent, IntentResult
from customer_service.graph.routing import route_after_intent, route_after_guard, route_after_slot_check
from customer_service.graph.state import AgentState
from customer_service.tasking.models import TaskFrame, TaskStatus


class TestRouteAfterIntent:
    """测试 intent_parse 之后的路由"""
    
    def test_accept_routes_to_check_slots(self):
        """ACCEPT 动作应该路由到 check_slots"""
        state: AgentState = {
            "turn_id": "test-001",
            "turn_action": TurnAction.ACCEPT,
        }
        
        result = route_after_intent(state)
        assert result == "check_slots", "ACCEPT 应该路由到 check_slots"
    
    def test_clarify_routes_to_respond(self):
        """CLARIFY 动作应该路由到 respond"""
        state: AgentState = {
            "turn_id": "test-002",
            "turn_action": TurnAction.CLARIFY,
        }
        
        result = route_after_intent(state)
        assert result == "respond", "CLARIFY 应该路由到 respond"
    
    def test_chitchat_routes_to_respond(self):
        """CHITCHAT 动作应该路由到 respond"""
        state: AgentState = {
            "turn_id": "test-003",
            "turn_action": TurnAction.CHITCHAT,
        }
        
        result = route_after_intent(state)
        assert result == "respond", "CHITCHAT 应该路由到 respond"
    
    def test_cancel_routes_to_respond(self):
        """CANCEL 动作应该路由到 respond"""
        state: AgentState = {
            "turn_id": "test-004",
            "turn_action": TurnAction.CANCEL,
        }
        
        result = route_after_intent(state)
        assert result == "respond", "CANCEL 应该路由到 respond"
    
    def test_select_intent_routes_to_respond(self):
        """SELECT_INTENT 动作应该路由到 respond"""
        state: AgentState = {
            "turn_id": "test-005",
            "turn_action": TurnAction.SELECT_INTENT,
        }
        
        result = route_after_intent(state)
        assert result == "respond", "SELECT_INTENT 应该路由到 respond"
    
    def test_missing_turn_action_raises_error(self):
        """缺失 turn_action 应该抛出错误"""
        state: AgentState = {
            "turn_id": "test-006",
            "turn_action": None,
        }
        
        with pytest.raises(ValueError, match="turn_action 未设置"):
            route_after_intent(state)
    
    def test_unknown_turn_action_raises_error(self):
        """未知的 turn_action 应该抛出错误"""
        state: AgentState = {
            "turn_id": "test-007",
            "turn_action": "unknown_action",  # 故意传入非法值
        }
        
        with pytest.raises(ValueError, match="未知的 turn_action"):
            route_after_intent(state)


class TestRouteAfterGuard:
    """测试 hallucination_guard 之后的路由"""
    
    def test_pass_routes_to_pass(self):
        """PASS 状态应该路由到 pass"""
        state: AgentState = {
            "turn_id": "test-101",
            "guard_status": GuardStatus.PASS,
        }
        
        result = route_after_guard(state)
        assert result == "pass", "PASS 应该路由到 pass"
    
    def test_fallback_routes_to_fallback(self):
        """FALLBACK 状态应该路由到 fallback"""
        state: AgentState = {
            "turn_id": "test-102",
            "guard_status": GuardStatus.FALLBACK,
        }
        
        result = route_after_guard(state)
        assert result == "fallback", "FALLBACK 应该路由到 fallback"
    
    def test_retry_routes_to_retry(self):
        """RETRY 状态应该路由到 retry"""
        state: AgentState = {
            "turn_id": "test-103",
            "guard_status": GuardStatus.RETRY,
        }
        
        result = route_after_guard(state)
        assert result == "retry", "RETRY 应该路由到 retry"
    
    def test_missing_guard_status_raises_error(self):
        """缺失 guard_status 应该抛出错误"""
        state: AgentState = {
            "turn_id": "test-104",
            "guard_status": None,
        }
        
        with pytest.raises(ValueError, match="guard_status 未设置"):
            route_after_guard(state)
    
    def test_unknown_guard_status_raises_error(self):
        """未知的 guard_status 应该抛出错误"""
        state: AgentState = {
            "turn_id": "test-105",
            "guard_status": "hallucination_detected",  # 旧的错误值
        }
        
        with pytest.raises(ValueError, match="未知的 guard_status"):
            route_after_guard(state)


class TestRouteAfterSlotCheck:
    """测试 slot_check 之后的路由"""
    
    def test_resumed_this_turn_routes_to_respond(self):
        """resumed_this_turn=True 应该路由到 respond"""
        state: AgentState = {
            "turn_id": "test-201",
            "resumed_this_turn": True,
            "active_task": None,
        }
        
        result = route_after_slot_check(state)
        assert result == "respond", "resumed_this_turn=True 应该路由到 respond"
    
    def test_missing_slots_routes_to_respond(self):
        """有缺失槽位应该路由到 respond"""
        task = TaskFrame(
            task_id="task-001",
            intent=BusinessIntent.PRODUCT_QUERY,
            status=TaskStatus.WAITING_SLOT,
            missing_slots=["product_id"],
            slots={},
            created_turn_id="turn-001",
            last_turn_id="turn-001",
        )

        state: AgentState = {
            "turn_id": "test-202",
            "resumed_this_turn": False,
            "active_task": task,
        }

        result = route_after_slot_check(state)
        assert result == "respond", "missing_slots 非空应该路由到 respond"

    def test_ready_task_routes_to_execute(self):
        """READY 状态且无缺失槽位应该路由到 execute"""
        task = TaskFrame(
            task_id="task-002",
            intent=BusinessIntent.PRODUCT_QUERY,
            status=TaskStatus.READY,
            missing_slots=[],
            slots={"product_id": "15970"},
            created_turn_id="turn-002",
            last_turn_id="turn-002",
        )
        
        intent_result = IntentResult(
            recognized=True,
            intent=BusinessIntent.PRODUCT_QUERY,
            decision=IntentDecision.ACCEPT,
        )
        
        state: AgentState = {
            "turn_id": "test-203",
            "resumed_this_turn": False,
            "active_task": task,
            "intent_result": intent_result,
        }
        
        result = route_after_slot_check(state)
        assert result == "execute", "READY 且槽位齐全应该路由到 execute"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
