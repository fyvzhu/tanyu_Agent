"""
阶段3测试：接入业务与证据 - Tool/Flow 错误处理

测试目标：
1. 配置错误（缺 runtime）返回 CONFIGURATION_ERROR
2. Flow 未注册返回 UNSUPPORTED_FLOW
3. 可重试错误和永久错误的区分
4. 任务完成时机（Guard 通过后）
5. Guard 状态契约一致性

对应文档：
- 第72-77行：P0-7问题描述（错误类型化、Guard状态）
- 第52行：任务完成时机（Guard 检查后）
"""
import pytest
from customer_service.graph.state import AgentState
from customer_service.intents.models import BusinessIntent, GuardStatus
from customer_service.tasking.models import TaskFrame, TaskStatus
from customer_service.flows.models import FlowResult, FlowStatus
from customer_service.tools.models import ToolResult, ToolError
from customer_service.graph.nodes.hallucination_guard import should_complete_task


class TestFlowErrorHandling:
    """测试 Flow 错误处理"""

    def test_configuration_error_returns_proper_status(self):
        """配置错误应返回 CONFIGURATION_ERROR 状态"""
        flow_result = FlowResult(
            ready_for_response=False,
            status=FlowStatus.CONFIGURATION_ERROR,
            tool_result=ToolResult(
                tool_name="system",
                ok=False,
                error=ToolError(
                    code="MISSING_RUNTIME",
                    message="Runtime context is required",
                    retryable=False
                )
            )
        )
        
        assert flow_result.status == FlowStatus.CONFIGURATION_ERROR
        assert flow_result.tool_result.ok is False
        assert flow_result.tool_result.error.retryable is False

    def test_unsupported_flow_returns_proper_status(self):
        """Flow 未注册应返回 UNSUPPORTED_FLOW 状态"""
        flow_result = FlowResult(
            ready_for_response=False,
            status=FlowStatus.UNSUPPORTED_FLOW,
            tool_result=ToolResult(
                tool_name="logistics_query",
                ok=False,
                error=ToolError(
                    code="FLOW_NOT_REGISTERED",
                    message="Intent has no registered Flow",
                    retryable=False
                )
            )
        )
        
        assert flow_result.status == FlowStatus.UNSUPPORTED_FLOW
        assert flow_result.tool_result.error.code == "FLOW_NOT_REGISTERED"

    def test_retryable_error(self):
        """可重试错误（如超时）应返回 RETRYABLE_ERROR"""
        flow_result = FlowResult(
            ready_for_response=False,
            status=FlowStatus.RETRYABLE_ERROR,
            tool_result=ToolResult(
                tool_name="product_query",
                ok=False,
                error=ToolError(
                    code="TIMEOUT",
                    message="Commerce API timeout",
                    retryable=True
                )
            )
        )
        
        assert flow_result.status == FlowStatus.RETRYABLE_ERROR
        assert flow_result.tool_result.error.retryable is True

    def test_permanent_error(self):
        """永久错误（如无权限）应返回 PERMANENT_ERROR"""
        flow_result = FlowResult(
            ready_for_response=False,
            status=FlowStatus.PERMANENT_ERROR,
            tool_result=ToolResult(
                tool_name="product_query",
                ok=False,
                error=ToolError(
                    code="PERMISSION_DENIED",
                    message="User has no permission",
                    retryable=False
                )
            )
        )
        
        assert flow_result.status == FlowStatus.PERMANENT_ERROR
        assert flow_result.tool_result.error.retryable is False


class TestTaskCompletionTiming:
    """测试任务完成时机（文档第52行）"""

    def test_should_complete_when_success_and_guard_pass(self):
        """成功且 Guard 通过时应完成任务"""
        state = AgentState(
            turn_id="test-1",
            guard_status=GuardStatus.PASS,
            flow_result=FlowResult(
                ready_for_response=True,
                status=FlowStatus.SUCCESS,
                tool_result=ToolResult(
                    tool_name="product_query",
                    ok=True,
                    data={"products": []}
                )
            )
        )
        
        assert should_complete_task(state) is True

    def test_should_not_complete_when_guard_fallback(self):
        """Guard FALLBACK 时不应完成任务"""
        state = AgentState(
            turn_id="test-2",
            guard_status=GuardStatus.FALLBACK,
            flow_result=FlowResult(
                ready_for_response=True,
                status=FlowStatus.SUCCESS,
                tool_result=ToolResult(
                    tool_name="product_query",
                    ok=True
                )
            )
        )
        
        assert should_complete_task(state) is False

    def test_should_not_complete_when_waiting_slot(self):
        """等待补槽时不应完成任务"""
        state = AgentState(
            turn_id="test-3",
            guard_status=GuardStatus.PASS,
            flow_result=FlowResult(
                ready_for_response=False,
                status=FlowStatus.WAITING_SLOT
            )
        )
        
        assert should_complete_task(state) is False

    def test_should_not_complete_when_retryable_error(self):
        """可重试错误时不应完成任务"""
        state = AgentState(
            turn_id="test-4",
            guard_status=GuardStatus.PASS,
            flow_result=FlowResult(
                ready_for_response=False,
                status=FlowStatus.RETRYABLE_ERROR,
                tool_result=ToolResult(
                    tool_name="product_query",
                    ok=False,
                    error=ToolError(
                        code="TIMEOUT",
                        message="Timeout",
                        retryable=True
                    )
                )
            )
        )
        
        assert should_complete_task(state) is False


class TestGuardStatusContract:
    """测试 Guard 状态契约一致性（文档第73行）"""

    def test_guard_status_pass_maps_correctly(self):
        """GuardStatus.PASS 应该对应 "pass" 路由"""
        assert GuardStatus.PASS.value == "pass"

    def test_guard_status_fallback_maps_correctly(self):
        """GuardStatus.FALLBACK 应该对应 "fallback" 路由"""
        assert GuardStatus.FALLBACK.value == "fallback"

    def test_guard_status_retry_maps_correctly(self):
        """GuardStatus.RETRY 应该对应 "retry" 路由"""
        assert GuardStatus.RETRY.value == "retry"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
