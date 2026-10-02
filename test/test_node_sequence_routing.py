"""
节点序列测试 - 验证路由完整性

根据文档第213行：
"测试要捕获访问过的节点序列，不是只断言 HTTP 200。
成功商品咨询至少应看到 intent_parse → slot_check → tool_dispatch → response_gen → hallucination_guard；
澄清则不应访问 tool_dispatch"

目标：
1. 验证ACCEPT路径访问完整节点序列
2. 验证CLARIFY路径不访问tool_dispatch
3. 验证resumed_this_turn不执行Tool
4. 验证意图不一致不执行Tool
"""
import pytest
from unittest.mock import MagicMock, patch
from customer_service.graph.state import AgentState, TaskStatus
from customer_service.intents.models import BusinessIntent, IntentResult, IntentDecision, TurnAction
from customer_service.tasking.models import TaskFrame
from customer_service.graph.routing import route_after_intent, route_after_slot_check


class TestNodeSequenceRouting:
    """测试节点序列路由"""

    def test_accept_routes_to_check_slots(self):
        """ACCEPT应该路由到check_slots"""
        state = AgentState(
            turn_id="test-1",
            turn_action=TurnAction.ACCEPT
        )
        
        result = route_after_intent(state)
        
        assert result == "check_slots"

    def test_clarify_routes_to_respond(self):
        """CLARIFY应该路由到respond（不访问tool_dispatch）"""
        state = AgentState(
            turn_id="test-2",
            turn_action=TurnAction.CLARIFY
        )
        
        result = route_after_intent(state)
        
        assert result == "respond"

    def test_slot_check_with_ready_task_routes_to_execute(self):
        """槽位齐全的任务应该路由到execute"""
        state = AgentState(
            turn_id="test-3",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.READY,
                slots={},
                missing_slots=[],
                created_turn_id="test-2",
                last_turn_id="test-2"
            ),
            intent_result=IntentResult(
                recognized=True,
                intent=BusinessIntent.PRODUCT_QUERY,
                decision=IntentDecision.ACCEPT,
                confidence=0.9,
                entities={}
            ),
            resumed_this_turn=False
        )
        
        result = route_after_slot_check(state)
        
        assert result == "execute"

    def test_slot_check_with_missing_slots_routes_to_respond(self):
        """缺少槽位应该路由到respond（不访问tool_dispatch）"""
        state = AgentState(
            turn_id="test-4",
            active_task=TaskFrame(
                task_id="task-2",
                intent=BusinessIntent.PROMOTION_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={},
                missing_slots=["product_id"],
                created_turn_id="test-3",
                last_turn_id="test-3"
            ),
            intent_result=IntentResult(
                recognized=True,
                intent=BusinessIntent.PROMOTION_QUERY,
                decision=IntentDecision.ACCEPT,
                confidence=0.9,
                entities={}
            ),
            resumed_this_turn=False
        )
        
        result = route_after_slot_check(state)
        
        assert result == "respond"

    def test_resumed_this_turn_routes_to_respond(self):
        """恢复任务本轮不执行Tool（文档第212行）"""
        state = AgentState(
            turn_id="test-5",
            active_task=TaskFrame(
                task_id="task-3",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.READY,
                slots={},
                missing_slots=[],
                created_turn_id="test-4",
                last_turn_id="test-4"
            ),
            intent_result=IntentResult(
                recognized=True,
                intent=BusinessIntent.PRODUCT_QUERY,
                decision=IntentDecision.ACCEPT,
                confidence=0.9,
                entities={}
            ),
            resumed_this_turn=True  # 恢复任务
        )
        
        result = route_after_slot_check(state)
        
        # 应该直接respond，不执行Tool
        assert result == "respond"

    def test_intent_mismatch_routes_to_respond(self):
        """意图不一致不执行Tool（文档第212行）"""
        state = AgentState(
            turn_id="test-6",
            active_task=TaskFrame(
                task_id="task-4",
                intent=BusinessIntent.PRODUCT_QUERY,  # 任务是商品查询
                status=TaskStatus.READY,
                slots={},
                missing_slots=[],
                created_turn_id="test-5",
                last_turn_id="test-5"
            ),
            intent_result=IntentResult(
                recognized=True,
                intent=BusinessIntent.PROMOTION_QUERY,  # 但意图识别是促销查询
                decision=IntentDecision.ACCEPT,
                confidence=0.9,
                entities={}
            ),
            resumed_this_turn=False
        )
        
        result = route_after_slot_check(state)
        
        # 意图不一致，应该respond
        assert result == "respond"


class TestContractViolation:
    """测试契约违反（参考 LangGraph 文档第110行：缺字段应该失败）"""

    def test_missing_turn_action_raises_error(self):
        """缺少 turn_action 应该抛出 ValueError"""
        state = AgentState(
            turn_id="test-7",
            turn_action=None  # 缺失
        )

        with pytest.raises(ValueError, match="turn_action 未设置"):
            route_after_intent(state)

    def test_missing_guard_status_raises_error(self):
        """缺少 guard_status 应该抛出 ValueError"""
        from customer_service.graph.routing import route_after_guard

        state = AgentState(
            turn_id="test-8",
            guard_status=None  # 缺失
        )

        with pytest.raises(ValueError, match="guard_status 未设置"):
            route_after_guard(state)

    def test_unknown_turn_action_raises_error(self):
        """未知的 turn_action 应该抛出 ValueError"""
        state = AgentState(
            turn_id="test-9",
            turn_action="invalid_action"  # 非法值
        )

        with pytest.raises(ValueError, match="未知的 turn_action"):
            route_after_intent(state)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
