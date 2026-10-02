"""
Intent Decision Validator - 意图决策验证器

设计原则（参考 ecommerce-customer-service/TurnPlanValidator）：
- 分类器提出候选目标（IntentClassificationResult）
- 验证器根据对话规则决定是否接受
- 输出 TurnDecision（包含 TurnAction）

验证规则：
1. 多目标冲突检查
2. 能力开放检查（当前Slice只开放部分意图）
3. 闲聊不启动任务
4. 低置信度拒绝
"""
from loguru import logger

from customer_service.intents.models import (
    IntentClassificationResult,
    IntentGoal,
    TurnDecision,
    TurnAction,
    BusinessIntent,
)
from customer_service.graph.state import AgentState
from customer_service.tasking.commands import (
    TaskCommand,
    StartTaskCommand,
    ContinueTaskCommand,
)


# 当前Slice开放的意图（参考文档：只有商品咨询、促销查询、催拍催付、闲聊可推进）
SUPPORTED_INTENTS = {
    BusinessIntent.PRODUCT_QUERY,
    BusinessIntent.PROMOTION_QUERY,
    BusinessIntent.URGE_ORDER_PAYMENT,
    BusinessIntent.CHITCHAT,
}

# 命令白名单（参考 TurnPlanValidator._validate_task_track）
ALLOWED_COMMAND_TYPES = {
    "start_task",      # StartTaskCommand
    "set_slots",       # SetSlotsCommand
    "resume_task",     # ResumeTaskCommand
    "cancel_task",     # CancelTaskCommand
    "complete_task",   # CompleteTaskCommand
    "continue_task",   # ContinueTaskCommand
}


class IntentDecisionValidator:
    """
    意图决策验证器
    
    参考 ecommerce-customer-service/TurnPlanValidator
    """
    
    def validate(
        self,
        state: AgentState,
        classification: IntentClassificationResult,
    ) -> TurnDecision:
        """
        验证分类器的输出，返回最终决策
        
        Args:
            state: 当前对话状态
            classification: 分类器输出
            
        Returns:
            TurnDecision: 最终决策
        """
        turn_id = state.get("turn_id", "unknown")
        
        # 规则1：分类器失败
        if classification.classifier_error:
            logger.warning(f"[{turn_id}] ❌ 分类器失败: {classification.classifier_error}")
            return TurnDecision(
                action=TurnAction.CLASSIFIER_FAILURE,
                reason=f"分类器错误: {classification.classifier_error}",
            )
        
        # 规则2：超出范围
        if classification.is_out_of_scope:
            logger.info(f"[{turn_id}] 🚫 超出范围")
            return TurnDecision(
                action=TurnAction.OUT_OF_SCOPE,
                reason="用户请求超出客服范围",
            )
        
        # 规则3：低置信度
        if not classification.is_confident:
            logger.info(f"[{turn_id}] ❓ 低置信度，需要澄清")
            return TurnDecision(
                action=TurnAction.CLARIFY,
                reason="分类置信度过低",
                clarify_message="抱歉，我没有完全理解您的意思，能否详细说明一下？",
            )
        
        # 规则4：无目标
        if not classification.goals:
            logger.warning(f"[{turn_id}] ⚠️ 分类器未返回任何目标")
            return TurnDecision(
                action=TurnAction.CLARIFY,
                reason="未识别到明确意图",
                clarify_message="请问您需要什么帮助？",
            )
        
        # 规则5：多目标冲突（参考 TurnPlanValidator.MULTIPLE_TRACKS）
        if len(classification.goals) > 1:
            # 检查是否有业务意图冲突
            business_goals = [g for g in classification.goals if g.intent != BusinessIntent.CHITCHAT]
            if len(business_goals) > 1:
                logger.info(f"[{turn_id}] 🔀 检测到多个业务目标，需要用户选择")
                return TurnDecision(
                    action=TurnAction.SELECT_INTENT,
                    reason="多个独立目标",
                    clarify_options=business_goals,
                    clarify_message="我理解您可能有多个需求，请选择优先处理的：",
                )
        
        # 规则6：单个目标验证
        goal = classification.goals[0]
        
        # 规则6.1：能力开放检查
        if goal.intent not in SUPPORTED_INTENTS:
            logger.info(f"[{turn_id}] 🚧 意图 {goal.intent.value} 暂未开放")
            return TurnDecision(
                action=TurnAction.UNSUPPORTED,
                reason=f"意图 {goal.intent.value} 当前未开放",
                clarify_message="抱歉，该功能暂未开放，我可以帮您查询商品信息、促销活动或订单状态。",
            )
        
        # 规则6.2：闲聊不启动任务（参考文档 P0-6）
        if goal.intent == BusinessIntent.CHITCHAT:
            logger.info(f"[{turn_id}] 💬 闲聊，不启动任务")
            return TurnDecision(
                action=TurnAction.CHITCHAT,
                reason="闲聊轨道",
                accepted_goal=goal,
                commands=[],  # 闲聊不生成任何命令
            )

        # 规则7：接受目标，生成 StartTaskCommand
        logger.info(f"[{turn_id}] ✅ 接受目标: {goal.intent.value}")
        commands = [
            StartTaskCommand(
                intent=goal.intent,
                entities=goal.entities,
            )
        ]

        # 规则8：命令白名单和多Flow检查（参考 TurnPlanValidator）
        validation_error = self._validate_commands(commands, turn_id)
        if validation_error:
            return validation_error

        return TurnDecision(
            action=TurnAction.ACCEPT,
            reason="单一明确目标",
            accepted_goal=goal,
            commands=commands,
        )

    def _validate_commands(
        self,
        commands: list[TaskCommand],
        turn_id: str,
    ) -> TurnDecision | None:
        """
        验证命令列表（参考 TurnPlanValidator._validate_task_track）

        检查：
        1. 命令是否在白名单内
        2. 是否有多个 StartTaskCommand（同时启动多个Flow）

        Returns:
            如果验证失败返回 TurnDecision，否则返回 None
        """
        if not commands:
            return None

        # 检查1：命令白名单
        for cmd in commands:
            if cmd.command_type not in ALLOWED_COMMAND_TYPES:
                logger.error(f"[{turn_id}] ❌ 非法命令类型: {cmd.command_type}")
                return TurnDecision(
                    action=TurnAction.CLARIFY,
                    reason=f"非法命令类型: {cmd.command_type}",
                    clarify_message="系统错误，请稍后重试。",
                )

        # 检查2：多Flow启动检测
        start_commands = [cmd for cmd in commands if isinstance(cmd, StartTaskCommand)]
        if len(start_commands) > 1:
            intents = [cmd.intent.value for cmd in start_commands]
            logger.warning(f"[{turn_id}] ⚠️ 检测到多个Flow启动命令: {intents}")
            return TurnDecision(
                action=TurnAction.CLARIFY,
                reason="同时启动多个Flow",
                clarify_message="抱歉，我一次只能处理一个任务，请选择优先处理的需求。",
            )

        return None
