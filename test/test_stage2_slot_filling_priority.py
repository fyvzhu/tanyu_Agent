"""
阶段2测试：等待槽位优先 + 智能槽位补填（P0-4修复）

测试目标：
1. 等待槽位时，短回复优先解析为槽位答案
2. 区分价格、商品编号、序数指代
3. 多个疑似编号时拒绝自动选择
4. 明确新目标时切换任务

对应文档：
- 第39-44行：P0-4问题描述
- 第193-194行：等待槽位优先规则
"""
import pytest
from customer_service.graph.state import AgentState, TaskStatus
from customer_service.intents.models import BusinessIntent
from customer_service.tasking.models import TaskFrame
from customer_service.graph.nodes.intent_parse import (
    _is_new_explicit_goal,
    _try_fill_missing_slots,
)


class TestIsNewExplicitGoal:
    """测试明确新目标检测"""

    def test_pure_number_not_new_goal(self):
        """纯数字不是新目标"""
        assert not _is_new_explicit_goal("15970")
        assert not _is_new_explicit_goal("500")

    def test_price_expression_not_new_goal(self):
        """价格表达不是新目标"""
        assert not _is_new_explicit_goal("500元")
        assert not _is_new_explicit_goal("预算500")
        assert not _is_new_explicit_goal("500以内")

    def test_color_not_new_goal(self):
        """颜色词不是新目标"""
        assert not _is_new_explicit_goal("红色")
        assert not _is_new_explicit_goal("黑色")

    def test_ordinal_not_new_goal(self):
        """序数不是新目标"""
        assert not _is_new_explicit_goal("第一个")
        assert not _is_new_explicit_goal("第二个")

    def test_confirmation_not_new_goal(self):
        """确认词不是新目标"""
        assert not _is_new_explicit_goal("是")
        assert not _is_new_explicit_goal("好的")
        assert not _is_new_explicit_goal("确认")

    def test_explicit_goal_keywords(self):
        """包含业务关键词的是新目标"""
        assert _is_new_explicit_goal("推荐红色跑鞋")
        assert _is_new_explicit_goal("查一下优惠")
        assert _is_new_explicit_goal("看看物流")
        assert _is_new_explicit_goal("我要买T恤")


class TestTryFillMissingSlots:
    """测试智能槽位补填"""

    def test_single_product_id_success(self):
        """单个商品编号，成功补填"""
        state = AgentState(turn_id="test-1", current_message="15970")
        task = TaskFrame(
            task_id="task-1",
            intent=BusinessIntent.PROMOTION_QUERY,
            status=TaskStatus.WAITING_SLOT,
            slots={},
            missing_slots=["product_id"],
            created_turn_id="test-0",
            last_turn_id="test-0",
        )
        
        result = _try_fill_missing_slots(state, task, "15970", "test-1")
        
        assert result is True
        assert task.slots["product_id"] == "15970"
        assert "product_id" not in task.missing_slots

    def test_price_and_product_id_reject_first(self):
        """文档第39行案例：'预算500，商品15970' 不应取第一个数字500"""
        state = AgentState(turn_id="test-2", current_message="预算500，商品15970")
        task = TaskFrame(
            task_id="task-2",
            intent=BusinessIntent.PROMOTION_QUERY,
            status=TaskStatus.WAITING_SLOT,
            slots={},
            missing_slots=["product_id"],
            created_turn_id="test-0",
            last_turn_id="test-0",
        )
        
        # 由于包含"预算"关键词，应该拒绝解析为商品编号
        result = _try_fill_missing_slots(state, task, "预算500，商品15970", "test-2")
        
        assert result is False
        assert "product_id" not in task.slots

    def test_multiple_product_ids_reject(self):
        """文档第39行案例：'15970和39386哪款有优惠' 不应自动选择"""
        state = AgentState(turn_id="test-3", current_message="15970和39386哪款有优惠")
        task = TaskFrame(
            task_id="task-3",
            intent=BusinessIntent.PROMOTION_QUERY,
            status=TaskStatus.WAITING_SLOT,
            slots={},
            missing_slots=["product_id"],
            created_turn_id="test-0",
            last_turn_id="test-0",
        )

        result = _try_fill_missing_slots(state, task, "15970和39386哪款有优惠", "test-3")

        assert result is False
        assert "product_id" not in task.slots

    def test_short_number_reject(self):
        """3位以下数字不是商品编号"""
        state = AgentState(turn_id="test-4", current_message="500")
        task = TaskFrame(
            task_id="task-4",
            intent=BusinessIntent.PROMOTION_QUERY,
            status=TaskStatus.WAITING_SLOT,
            slots={},
            missing_slots=["product_id"],
            created_turn_id="test-0",
            last_turn_id="test-0",
        )

        result = _try_fill_missing_slots(state, task, "500", "test-4")

        assert result is False

    def test_order_id_success(self):
        """订单号补填（8位以上）"""
        state = AgentState(turn_id="test-5", current_message="12345678")
        task = TaskFrame(
            task_id="task-5",
            intent=BusinessIntent.LOGISTICS_QUERY,
            status=TaskStatus.WAITING_SLOT,
            slots={},
            missing_slots=["order_id"],
            created_turn_id="test-0",
            last_turn_id="test-0",
        )
        
        result = _try_fill_missing_slots(state, task, "12345678", "test-5")
        
        assert result is True
        assert task.slots["order_id"] == "12345678"
        assert "order_id" not in task.missing_slots


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
