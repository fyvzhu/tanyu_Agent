"""
Intent 模型定义
根据 01_slice_foundation 文档 #18-21 定义
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from customer_service.tasking.models import BusinessIntent, ActionMode


class IntentDecision(str, Enum):
    """Intent 决策结果 - 问题4修复: 删除 MULTIPLE_INTENTS，只保留四种决策"""
    ACCEPT = "accept"
    CLARIFY = "clarify"
    OUT_OF_SCOPE = "out_of_scope"
    CLASSIFIER_FAILURE = "classifier_failure"


class IntentFallbackReason(str, Enum):
    """Intent 回退原因"""
    LOW_CONFIDENCE = "low_confidence"
    OUT_OF_SCOPE = "out_of_scope"
    CLASSIFIER_FAILURE = "classifier_failure"
    MULTIPLE_INTENTS = "multiple_intents"


# ==================== 阶段1重构：分类器输出层 ====================

class IntentGoal(BaseModel):
    """
    单个意图目标 - 分类器输出的原子单位
    一个用户消息可能包含多个目标（如"查订单并推荐商品"）
    """
    intent: BusinessIntent = Field(..., description="识别的业务意图")
    entities: dict[str, Any] = Field(default_factory=dict, description="提取的实体")
    text_span: str | None = Field(None, description="对应的原句片段")
    confidence: float | None = Field(None, description="该目标的置信度")


class IntentClassificationResult(BaseModel):
    """
    分类器的原始输出 - 不做决策，只提供候选

    设计原则（参考 ecommerce-customer-service TurnPlan）：
    - 分类器提出候选目标，不决定是否执行
    - 可能包含多个目标（MULTIPLE_INTENTS）
    - 可能低置信度（LOW_CONFIDENCE）
    - 可能超出范围（OUT_OF_SCOPE）
    """
    goals: list[IntentGoal] = Field(default_factory=list, description="识别的目标列表")
    is_confident: bool = Field(..., description="是否高置信度")
    is_out_of_scope: bool = Field(False, description="是否超出范围")
    classifier_error: str | None = Field(None, description="分类器错误信息")
    raw_response: dict[str, Any] | None = Field(None, description="LLM原始响应")


# ==================== 原有 TurnAction 和 GuardStatus（保留）====================


class TurnAction(str, Enum):
    """
    本轮动作类型 - 阶段1修复
    表示图的下一步动作，由 intent_parse 节点设置，由路由函数消费
    """
    ACCEPT = "accept"                      # 接受意图，进入槽位检查
    CLARIFY = "clarify"                    # 需要澄清（低置信度、缺对象等）
    SELECT_INTENT = "select_intent"        # 多个独立目标，等待用户选择
    CHITCHAT = "chitchat"                  # 闲聊，直接回复
    CANCEL = "cancel"                      # 取消当前任务
    RESUME_NOTICE = "resume_notice"        # 恢复任务提示
    UNSUPPORTED = "unsupported"            # 识别了但当前未开放
    CLASSIFIER_FAILURE = "classifier_failure"  # 分类器失败
    OUT_OF_SCOPE = "out_of_scope"          # 超出范围


class GuardStatus(str, Enum):
    """
    Guard 检查状态 - 阶段1修复
    统一 hallucination_guard 节点和路由函数的状态值
    """
    PASS = "pass"          # 检查通过
    RETRY = "retry"        # 需要重新生成
    FALLBACK = "fallback"  # 使用兜底回复


# ==================== 阶段1重构：验证器输出层 ====================

class TurnDecision(BaseModel):
    """
    验证器的决策输出 - 基于规则判断分类器的提议是否可接受

    设计原则（参考 ecommerce-customer-service TurnPlanValidator）：
    - 验证器根据对话规则决定是否接受分类器的提议
    - 检查多目标冲突、命令白名单、能力开放等
    - 输出最终的 TurnAction 供路由使用
    - 输出命令列表供 CommandProcessor 执行
    """
    action: TurnAction = Field(..., description="本轮动作")
    reason: str | None = Field(None, description="决策原因")
    accepted_goal: IntentGoal | None = Field(None, description="接受的目标（ACCEPT时非空）")
    clarify_options: list[IntentGoal] | None = Field(None, description="澄清选项（SELECT_INTENT时非空）")
    clarify_message: str | None = Field(None, description="澄清提示文本")
    commands: list = Field(default_factory=list, description="要执行的命令列表")


# ==================== 原有 IntentResult（保留兼容）====================


class IntentResult(BaseModel):
    """Intent 识别结果"""
    recognized: bool = Field(..., description="是否成功识别")
    intent: BusinessIntent | None = Field(None, description="识别到的意图")
    action_mode: ActionMode | None = Field(None, description="行动模式")
    decision: IntentDecision = Field(..., description="决策结果")
    fallback_reason: IntentFallbackReason | None = Field(None, description="回退原因")
    confidence: float | None = Field(None, description="置信度（非校准概率）")
    second_confidence: float | None = Field(None, description="第二候选置信度")
    margin: float | None = Field(None, description="置信度差值")
    candidate_intents: list[BusinessIntent] = Field(
        default_factory=list, 
        description="候选 Intent 列表（用于澄清）"
    )
    entities: dict[str, Any] = Field(default_factory=dict, description="提取的实体")


class IntentPolicy(BaseModel):
    """Intent 策略定义"""
    intent: BusinessIntent = Field(..., description="业务意图")
    allowed_tools: tuple[str, ...] = Field(default_factory=tuple, description="允许的 Tool 列表")
    can_write: bool = Field(False, description="是否可写")
    requires_action_request: bool = Field(False, description="是否要求 ACTION_REQUEST")
    requires_execute_confirmation: bool = Field(False, description="是否要求执行确认")
