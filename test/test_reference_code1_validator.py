"""
参考代码1验证 - ecommerce-customer-service
测试 TurnPlanValidator 的命令白名单和多Flow检查

根据文档第100-103行：
- 命令白名单检查：只允许特定命令类型
- 多Flow启动检测：同一轮不能有多个 StartTaskCommand
"""
import pytest
from customer_service.graph.state import AgentState
from customer_service.intents.models import (
    IntentClassificationResult,
    IntentGoal,
    BusinessIntent,
    TurnAction,
)
from customer_service.intents.validator import IntentDecisionValidator
from customer_service.tasking.commands import StartTaskCommand


class TestCommandWhitelist:
    """测试命令白名单（参考 TurnPlanValidator._validate_task_track）"""

    def test_start_task_command_is_allowed(self):
        """StartTaskCommand 应该通过白名单检查"""
        validator = IntentDecisionValidator()
        state = AgentState(turn_id="test-1")
        
        classification = IntentClassificationResult(
            goals=[
                IntentGoal(
                    intent=BusinessIntent.PRODUCT_QUERY,
                    confidence=0.9,
                    entities={"keyword": "鞋"}
                )
            ],
            is_confident=True,
            is_out_of_scope=False,
        )
        
        decision = validator.validate(state, classification)
        
        assert decision.action == TurnAction.ACCEPT
        assert len(decision.commands) == 1
        assert isinstance(decision.commands[0], StartTaskCommand)

    def test_invalid_command_type_rejected(self):
        """非法命令类型应该被拒绝"""
        validator = IntentDecisionValidator()
        state = AgentState(turn_id="test-2")
        
        # 创建一个包含非法命令的场景
        # 注意：这是防御性测试，正常流程不应产生非法命令
        from customer_service.tasking.commands import TaskCommand
        from pydantic import Field
        
        class InvalidCommand(TaskCommand):
            command_type: str = "invalid_type"
        
        invalid_cmd = InvalidCommand()
        
        result = validator._validate_commands([invalid_cmd], "test-2")
        
        assert result is not None
        assert result.action == TurnAction.CLARIFY
        assert "非法命令类型" in result.reason


class TestMultipleFlowDetection:
    """测试多Flow启动检测（参考 TurnPlanValidator 第89-91行）"""

    def test_single_flow_accepted(self):
        """单个Flow启动应该接受"""
        validator = IntentDecisionValidator()
        
        commands = [
            StartTaskCommand(
                intent=BusinessIntent.PRODUCT_QUERY,
                entities={"keyword": "鞋"}
            )
        ]
        
        result = validator._validate_commands(commands, "test-3")
        
        assert result is None  # 验证通过

    def test_multiple_flows_rejected(self):
        """多个Flow启动应该被拒绝"""
        validator = IntentDecisionValidator()
        
        commands = [
            StartTaskCommand(
                intent=BusinessIntent.PRODUCT_QUERY,
                entities={"keyword": "鞋"}
            ),
            StartTaskCommand(
                intent=BusinessIntent.PROMOTION_QUERY,
                entities={}
            )
        ]
        
        result = validator._validate_commands(commands, "test-4")
        
        assert result is not None
        assert result.action == TurnAction.CLARIFY
        assert "多个Flow" in result.reason


class TestValidatorIntegration:
    """集成测试：确保参考代码1的模式正确实现"""

    def test_business_goal_generates_valid_command(self):
        """业务目标应该生成有效的命令"""
        validator = IntentDecisionValidator()
        state = AgentState(turn_id="test-5")
        
        classification = IntentClassificationResult(
            goals=[
                IntentGoal(
                    intent=BusinessIntent.PROMOTION_QUERY,
                    confidence=0.85,
                    entities={"product_id": "12345"}
                )
            ],
            is_confident=True,
            is_out_of_scope=False,
        )
        
        decision = validator.validate(state, classification)
        
        # 验证决策
        assert decision.action == TurnAction.ACCEPT
        assert decision.accepted_goal is not None
        assert decision.accepted_goal.intent == BusinessIntent.PROMOTION_QUERY
        
        # 验证命令
        assert len(decision.commands) == 1
        cmd = decision.commands[0]
        assert isinstance(cmd, StartTaskCommand)
        assert cmd.intent == BusinessIntent.PROMOTION_QUERY
        assert cmd.entities["product_id"] == "12345"

    def test_chitchat_generates_no_command(self):
        """闲聊不生成命令（参考文档 P0-6）"""
        validator = IntentDecisionValidator()
        state = AgentState(turn_id="test-6")
        
        classification = IntentClassificationResult(
            goals=[
                IntentGoal(
                    intent=BusinessIntent.CHITCHAT,
                    confidence=0.9,
                    entities={}
                )
            ],
            is_confident=True,
            is_out_of_scope=False,
        )
        
        decision = validator.validate(state, classification)
        
        assert decision.action == TurnAction.CHITCHAT
        assert decision.commands == []  # 闲聊不生成命令


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
