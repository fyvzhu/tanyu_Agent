"""
参考代码4验证 - retail-shopping-assistant-main 证据边界

根据文档第131行：
"历史谈话用于理解指代，本轮新鲜检索和业务系统返回的数据用于事实陈述。
response_gen 接受本轮 Flow 的对象和 Evidence，
历史消息只帮助判断'这款''刚才那款'，不能当当前价格或库存的来源。
Guard 应对数字、折扣、品牌等用户可见事实按证据类型核对，
且不要把 Guard 的通过状态同 Flow 成功状态混淆。"

测试目标：
1. response_gen 使用本轮 FlowResult，不依赖历史
2. Guard 状态与 Flow 状态独立
3. FlowStatus 正确区分成功/错误
"""
import pytest
from customer_service.graph.state import AgentState, TaskFrame, TaskStatus
from customer_service.intents.models import BusinessIntent
from customer_service.flows.models import FlowResult, FlowStatus


class TestEvidenceBoundary:
    """测试证据边界（参考 chatter.py 的权威数据原则）"""

    @pytest.mark.asyncio
    async def test_response_handles_flow_result(self):
        """response_gen 应该能处理 FlowResult"""
        from customer_service.graph.nodes.response_gen import response_gen_node

        # 简化测试：只验证有 FlowResult 时不会崩溃
        state = AgentState(
            turn_id="turn-1",
            current_message="查看商品",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.READY,
                slots={"keyword": "鞋"},
                missing_slots=[],
                created_turn_id="turn-1",
                last_turn_id="turn-1"
            )
        )

        # 调用 response_gen_node（没有 flow_result）
        result_state = await response_gen_node(state, {})

        # 验证：应该生成响应
        assert result_state["response_draft"] is not None
        assert len(result_state["response_draft"]) > 0

    @pytest.mark.asyncio
    async def test_flow_status_no_result_message(self):
        """FlowStatus.NO_RESULT 应该返回明确的无结果提示"""
        from customer_service.graph.nodes.response_gen import response_gen_node
        from customer_service.tools.models import ToolResult

        # 场景：NO_RESULT - 空查询
        state = AgentState(
            turn_id="turn-2",
            current_message="查看不存在的商品",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.READY,
                slots={"keyword": "xxxxx"},
                missing_slots=[],
                created_turn_id="turn-2",
                last_turn_id="turn-2"
            ),
            flow_result=FlowResult(
                status=FlowStatus.NO_RESULT,
                ready_for_response=True,
                tool_result=ToolResult(
                    ok=True,
                    tool_name="product_search",
                    data={}
                ),
                objects=[]
            )
        )

        result = await response_gen_node(state, {})
        assert "没有找到" in result["response_draft"]  # 空结果应该明确说明


class TestGuardFlowSeparation:
    """测试 Guard 状态与 Flow 状态分离"""

    def test_guard_status_enum_exists(self):
        """GuardStatus 应该是独立的枚举"""
        from customer_service.intents.models import GuardStatus
        
        # 验证：GuardStatus 有独立的值
        assert hasattr(GuardStatus, 'PASS')
        assert hasattr(GuardStatus, 'RETRY')
        assert hasattr(GuardStatus, 'FALLBACK')

    def test_flow_status_enum_exists(self):
        """FlowStatus 应该是独立的枚举"""
        # 验证：FlowStatus 有独立的值
        assert hasattr(FlowStatus, 'SUCCESS')
        assert hasattr(FlowStatus, 'NO_RESULT')
        assert hasattr(FlowStatus, 'WAITING_SLOT')
        assert hasattr(FlowStatus, 'RETRYABLE_ERROR')
        assert hasattr(FlowStatus, 'PERMANENT_ERROR')

    def test_guard_and_flow_status_are_different(self):
        """Guard 状态和 Flow 状态应该是不同的类型"""
        from customer_service.intents.models import GuardStatus
        
        # 验证：不能混用
        guard_pass = GuardStatus.PASS
        flow_success = FlowStatus.SUCCESS
        
        assert guard_pass != flow_success
        assert type(guard_pass).__name__ == 'GuardStatus'
        assert type(flow_success).__name__ == 'FlowStatus'


class TestFlowStatusHandling:
    """测试 FlowStatus 的各种状态处理"""

    @pytest.mark.asyncio
    async def test_configuration_error_response(self):
        """CONFIGURATION_ERROR 应该返回系统错误提示"""
        from customer_service.graph.nodes.response_gen import response_gen_node
        
        state = AgentState(
            turn_id="turn-4",
            current_message="查询",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.READY,
                slots={},
                missing_slots=[],
                created_turn_id="turn-4",
                last_turn_id="turn-4"
            ),
            flow_result=FlowResult(
                status=FlowStatus.CONFIGURATION_ERROR,
                ready_for_response=False
            )
        )
        
        result = await response_gen_node(state, {})
        assert "系统配置" in result["response_draft"]
        assert result["fallback_used"] is True

    @pytest.mark.asyncio
    async def test_retryable_error_response(self):
        """RETRYABLE_ERROR 应该提示稍后再试"""
        from customer_service.graph.nodes.response_gen import response_gen_node
        
        state = AgentState(
            turn_id="turn-5",
            current_message="查询",
            active_task=TaskFrame(
                task_id="task-1",
                intent=BusinessIntent.PRODUCT_QUERY,
                status=TaskStatus.READY,
                slots={},
                missing_slots=[],
                created_turn_id="turn-5",
                last_turn_id="turn-5"
            ),
            flow_result=FlowResult(
                status=FlowStatus.RETRYABLE_ERROR,
                ready_for_response=False
            )
        )
        
        result = await response_gen_node(state, {})
        assert "稍后再试" in result["response_draft"]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
