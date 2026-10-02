"""
参考代码2验证 - LangGraph Checkpoint 恢复语义

根据文档第110行：
"Checkpoint 的部分用于验证恢复语义：
A 等槽位→另起 B→B 完成→读取 Checkpoint，
检查 Task ID、槽位、暂停栈顺序、待选择内容是否真正保存和恢复。
TurnInitializer 必须显式清理本轮字段"

测试目标：
1. 验证任务栈（active_task、paused_tasks）持久化
2. 验证槽位信息持久化
3. 验证 transient 字段每轮重置
4. 验证恢复后任务状态正确
"""
import pytest
from customer_service.graph.state import AgentState, TaskFrame, TaskStatus
from customer_service.intents.models import BusinessIntent
from customer_service.graph.turn_initializer import TurnInitializer


class TestTaskPersistence:
    """测试任务持久化（参考 LangGraph Checkpoint）"""

    def test_active_task_persists_across_turns(self):
        """active_task 应该跨轮次持久化"""
        # Turn 1: 创建任务
        state = AgentState(
            turn_id="turn-1",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={"keyword": "鞋"},
                missing_slots=["price_range"],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            )
        )
        
        # Turn 2: 初始化新轮次（模拟 Checkpoint 恢复）
        state = TurnInitializer.initialize_turn(
            state,
            current_message="500元以内",
            turn_id="turn-2"
        )
        
        # 验证：active_task 应该保留
        assert state["active_task"] is not None
        assert state["active_task"].task_id == "task-1"
        assert state["active_task"].intent == BusinessIntent.PRODUCT_QUERY
        assert state["active_task"].slots["keyword"] == "鞋"

    def test_paused_tasks_persists_as_stack(self):
        """paused_tasks 应该保持 LIFO 栈结构"""
        # Turn 1: A 任务被暂停，启动 B 任务
        state = AgentState(
            turn_id="turn-1",
            active_task=TaskFrame(
                task_id="task-B",
                intent=BusinessIntent.PROMOTION_QUERY,
                status=TaskStatus.READY,
                slots={},
                missing_slots=[],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            ),
            paused_tasks=[
                TaskFrame(
                    task_id="task-A",
                    intent=BusinessIntent.PRODUCT_QUERY,
                    status=TaskStatus.WAITING_SLOT,
                    slots={"keyword": "鞋"},
                    missing_slots=["price_range"],
                    created_turn_id="turn-0",
                    last_turn_id="turn-0"
                )
            ]
        )
        
        # Turn 2: 初始化新轮次
        state = TurnInitializer.initialize_turn(
            state,
            current_message="有促销吗",
            turn_id="turn-2"
        )
        
        # 验证：暂停栈应该保留
        assert len(state["paused_tasks"]) == 1
        assert state["paused_tasks"][0].task_id == "task-A"
        assert state["paused_tasks"][0].slots["keyword"] == "鞋"

    def test_pending_intent_selection_persists(self):
        """pending_intent_selection 应该持久化（用户选择多意图场景）"""
        state = AgentState(
            turn_id="turn-1",
            pending_intent_selection=[
                {"intent": "product_query", "entities": {"keyword": "鞋"}},
                {"intent": "promotion_query", "entities": {}}
            ]
        )
        
        # Turn 2: 初始化新轮次
        state = TurnInitializer.initialize_turn(
            state,
            current_message="第一个",
            turn_id="turn-2"
        )
        
        # 验证：待选择内容应该保留
        assert state["pending_intent_selection"] is not None
        assert len(state["pending_intent_selection"]) == 2


class TestTransientFieldsReset:
    """测试 Transient 字段重置（参考文档第110行）"""

    def test_transient_fields_reset_each_turn(self):
        """Transient 字段应该每轮重置"""
        # Turn 1: 有 transient 数据
        state = AgentState(
            turn_id="turn-1",
            current_message="查询商品",
            intent_result={"intent": "product_query"},
            entities={"keyword": "鞋"},
            flow_result={"status": "success"},
            response_draft="这是草稿",
            resumed_this_turn=True,
            guard_retry_count=2,
            fallback_used=True
        )
        
        # Turn 2: 初始化新轮次
        state = TurnInitializer.initialize_turn(
            state,
            current_message="新消息",
            turn_id="turn-2"
        )
        
        # 验证：所有 transient 字段应该重置
        assert state["turn_id"] == "turn-2"
        assert state["current_message"] == "新消息"
        assert state["intent_result"] is None
        assert state["entities"] == {}
        assert state["flow_result"] is None
        assert state["response_draft"] is None
        assert state["resumed_this_turn"] is False
        assert state["guard_retry_count"] == 0
        assert state["fallback_used"] is False


class TestCheckpointRecovery:
    """测试 Checkpoint 恢复场景"""

    def test_task_stack_recovery_after_interrupt(self):
        """任务中断后应该能正确恢复栈"""
        # 场景：A 等槽位 → 另起 B → B 完成 → 恢复 A
        
        # Turn 1: A 等槽位
        state_turn1 = AgentState(
            turn_id="turn-1",
            active_task=TaskFrame(
                task_id="task-A",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={"keyword": "鞋"},
                missing_slots=["price_range"],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            )
        )
        
        # Turn 2: 用户另起 B，A 被暂停
        state_turn2 = TurnInitializer.initialize_turn(
            state_turn1,
            current_message="查促销",
            turn_id="turn-2"
        )
        # 模拟 CommandProcessor 的暂停操作
        state_turn2["paused_tasks"] = [state_turn2["active_task"]]
        state_turn2["active_task"] = TaskFrame(
            task_id="task-B",
            intent=BusinessIntent.PROMOTION_QUERY,
            status=TaskStatus.READY,
            slots={},
            missing_slots=[],
            created_turn_id="turn-2",
            last_turn_id="turn-2"
        )
        
        # Turn 3: B 完成，恢复 A（模拟 Checkpoint 恢复）
        state_turn3 = TurnInitializer.initialize_turn(
            state_turn2,
            current_message="继续A",
            turn_id="turn-3"
        )
        
        # 验证：暂停栈应该保留 A
        assert len(state_turn3["paused_tasks"]) == 1
        assert state_turn3["paused_tasks"][0].task_id == "task-A"
        assert state_turn3["paused_tasks"][0].slots["keyword"] == "鞋"
        assert state_turn3["paused_tasks"][0].missing_slots == ["price_range"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
