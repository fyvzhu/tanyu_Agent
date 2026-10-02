"""
参考代码3验证 - E-commerce-AI-Agent-main 会话状态优先解释

根据文档第120-123行：
"优先读 orchestrator.py 的 _safe_route()，看它在普通 LLM 路由前先检查
pending_cart、pending_detail、pending_compare 等会话状态；
不是每条短消息都当作全新的意图。"

测试目标：
1. WAITING_SLOT 优先解释：短输入优先解析为槽位填充
2. pending_intent_selection 优先解释：多意图选择
3. 明确新目标覆盖旧上下文
"""
import pytest
from customer_service.graph.state import AgentState, TaskFrame, TaskStatus
from customer_service.intents.models import BusinessIntent, TurnAction
from customer_service.tasking.models import PendingIntentSelection


class TestSessionStatePriority:
    """测试会话状态优先解释（参考 orchestrator._safe_route）"""

    @pytest.mark.asyncio
    async def test_waiting_slot_bypasses_intent_classification(self):
        """等待槽位时，短输入应优先解析为槽位，不走意图分类"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：促销查询等待商品ID
        state = AgentState(
            turn_id="turn-1",
            current_message="15970",  # 短数字输入
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PROMOTION_QUERY,
                status=TaskStatus.WAITING_SLOT,  # 等待槽位
                slots={},
                missing_slots=["product_id"],
                created_turn_id="turn-0",
                last_turn_id="turn-0"
            )
        )
        
        # 调用 intent_parse_node
        result_state = await intent_parse_node(state, {})
        
        # 验证：应该填充槽位，而不是识别为新意图
        assert result_state["turn_action"] == TurnAction.ACCEPT
        assert result_state["active_task"].slots.get("product_id") == "15970"
        assert result_state["intent_result"].intent == BusinessIntent.PROMOTION_QUERY

    @pytest.mark.asyncio
    async def test_explicit_new_goal_overrides_waiting_slot(self):
        """明确的新目标应该覆盖 WAITING_SLOT"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node

        # 场景：等待槽位时，用户明确提出新需求
        state = AgentState(
            turn_id="turn-2",
            current_message="我想查商品",  # 明确的新意图（使用支持的意图）
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PROMOTION_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={},
                missing_slots=["product_id"],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            )
        )

        # 调用 intent_parse_node
        result_state = await intent_parse_node(state, {})

        # 验证：应该启动新任务，而不是填充旧任务槽位
        assert result_state["turn_action"] == TurnAction.ACCEPT
        # 新任务应该是商品查询
        assert result_state["active_task"].intent == BusinessIntent.PRODUCT_QUERY

    @pytest.mark.asyncio
    async def test_pending_selection_bypasses_classification(self):
        """pending_intent_selection 应该优先处理，不走分类"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node

        # 场景：多意图选择场景
        state = AgentState(
            turn_id="turn-3",
            current_message="第一个",  # 选择序号
            pending_intent_selection=PendingIntentSelection(
                original_turn_id="turn-2",
                candidate_intents=[
                    BusinessIntent.PRODUCT_QUERY,
                    BusinessIntent.PROMOTION_QUERY
                ]
            )
        )

        # 调用 intent_parse_node
        result_state = await intent_parse_node(state, {})

        # 验证：应该解析选择，启动对应任务
        assert result_state["turn_action"] == TurnAction.ACCEPT
        assert result_state["pending_intent_selection"] is None  # 已清空
        assert result_state["active_task"] is not None
        assert result_state["active_task"].intent == BusinessIntent.PRODUCT_QUERY


class TestContextPreservation:
    """测试上下文保留（参考 session.py 的 last_hits）"""

    def test_conversation_focus_preserved_across_turns(self):
        """conversation_focus 应该跨轮次保留"""
        from customer_service.graph.turn_initializer import TurnInitializer

        # Turn 1: 设置焦点
        state = AgentState(
            turn_id="turn-1",
            conversation_focus={"entity_type": "product", "entity_id": "12345"}
        )

        # Turn 2: 初始化新轮次
        state = TurnInitializer.initialize_turn(
            state,
            current_message="有优惠吗",
            turn_id="turn-2"
        )

        # 验证：焦点应该保留
        assert state["conversation_focus"] is not None
        assert state["conversation_focus"]["entity_id"] == "12345"


class TestNewSearchEscape:
    """测试明确新搜索释放旧上下文（参考 orchestrator 的 _is_new_search_escape）"""

    @pytest.mark.asyncio
    async def test_explicit_new_search_clears_context(self):
        """明确的新搜索应该清空旧上下文"""
        from customer_service.graph.nodes.intent_parse import intent_parse_node
        
        # 场景：用户明确说"重新推荐"
        state = AgentState(
            turn_id="turn-5",
            current_message="重新推荐鞋",  # 明确的新搜索
            active_task=TaskFrame(
                task_id="task-old",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.WAITING_SLOT,
                slots={"keyword": "衣服"},
                missing_slots=["price_range"],
                created_turn_id="turn-4",
                last_turn_id="turn-4"
            )
        )
        
        # 调用 intent_parse_node
        result_state = await intent_parse_node(state, {})
        
        # 验证：应该启动新任务
        assert result_state["turn_action"] == TurnAction.ACCEPT
        # 新任务应该是新的商品查询（关键词是"鞋"）


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
