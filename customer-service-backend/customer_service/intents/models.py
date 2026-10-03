"""
Intent 模型定义
根据 01_slice_foundation 文档 #18-21 定义

NLU_HYBRID_REFACTOR：新增 EntityCandidate、HybridIntentResult、HybridNLUSettings
用于混合意图识别（Rule + LLM）的数据结构。
"""
from enum import Enum
from typing import Any, Literal

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
    inherited: bool = Field(False, description="是否从上一轮继承的意图（P2修复）")


class IntentPolicy(BaseModel):
    """Intent 策略定义"""
    intent: BusinessIntent = Field(..., description="业务意图")
    allowed_tools: tuple[str, ...] = Field(default_factory=tuple, description="允许的 Tool 列表")
    can_write: bool = Field(False, description="是否可写")
    requires_action_request: bool = Field(False, description="是否要求 ACTION_REQUEST")
    requires_execute_confirmation: bool = Field(False, description="是否要求执行确认")


# ==================== NLU_HYBRID_REFACTOR：混合 NLU 数据结构 ====================


class EntityCandidate(BaseModel):
    """
    实体候选（带来源与置信度）

    NLU_HYBRID_REFACTOR：统一的实体表示，支持来源追踪与冲突融合。
    规则实体（source=rule）优先级高于 LLM 实体（source=llm）。
    """
    name: str = Field(..., description="实体名称，如 product_id / brand / color")
    value: Any = Field(..., description="实体值（原始字符串）")
    normalized_value: Any | None = Field(None, description="归一化后的值（可选）")

    source: Literal["rule", "llm", "context", "catalog", "fusion"] = Field(
        ..., description="实体来源"
    )

    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="置信度（0.0-1.0）"
    )

    text_span: str | None = Field(None, description="原文对应片段")
    validated: bool = Field(False, description="是否已通过业务验证（如品牌目录命中）")


class LLMEntity(BaseModel):
    """LLM 输出的实体（StructuredNLUOutput 内部使用）"""
    name: str = Field(..., description="实体名称")
    value: str = Field(..., description="实体值")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    text_span: str | None = None


class StructuredIntentGoal(BaseModel):
    """
    LLM 输出的单个意图目标（StructuredNLUOutput 内部使用）

    注意：与 IntentGoal（分类器通用格式）不同，
    这是 LLM 结构化输出专用的格式。
    """
    intent: BusinessIntent = Field(..., description="业务意图类型")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    text_span: str | None = None
    entities: list[LLMEntity] = Field(default_factory=list)


class StructuredNLUOutput(BaseModel):
    """
    LLM 结构化 NLU 输出（替代原来的 StructuredClassificationOutput）

    NLU_HYBRID_REFACTOR：统一 LLM NLU 的输出格式。
    reasoning 仅用于调试日志，不能作为业务控制依据。
    """
    goals: list[StructuredIntentGoal] = Field(default_factory=list)
    is_out_of_scope: bool = Field(False)
    needs_clarification: bool = Field(False)
    reasoning: str | None = Field(None, description="调试用推理（不用于路由决策）")


class HybridIntentResult(BaseModel):
    """
    混合意图识别结果

    NLU_HYBRID_REFACTOR：Hybrid NLU 的统一输出，包含来源、融合后的实体和可观测信息。
    """
    intent: BusinessIntent | None = Field(None)
    confidence: float = Field(..., ge=0.0, le=1.0)

    source: Literal["rule", "llm", "rule+llm", "context"] = Field(
        ..., description="意图来源"
    )

    margin: float | None = Field(None, description="置信度差值（rule top1 - top2）")
    ambiguous: bool = Field(False, description="是否存在意图歧义")

    entities: dict[str, EntityCandidate] = Field(
        default_factory=dict, description="融合后的实体字典，key 为实体名称"
    )

    llm_called: bool = Field(False, description="本轮是否调用了 LLM")
    llm_intent: BusinessIntent | None = Field(None, description="LLM 识别的意图（调试用）")
    llm_confidence: float | None = Field(None, description="LLM 置信度（调试用）")

    rule_intent: BusinessIntent | None = Field(None, description="规则识别的意图（调试用）")
    rule_confidence: float | None = Field(None, description="规则置信度（调试用）")

    fallback_used: bool = Field(False, description="是否使用了 fallback（LLM 失败降级）")
    is_out_of_scope: bool = Field(False)

    def to_entities_dict(self) -> dict[str, Any]:
        """
        将 EntityCandidate 字典转换为兼容旧代码的 dict[str, Any]。
        用于与现有 IntentResult.entities 兼容。
        """
        return {name: candidate.value for name, candidate in self.entities.items()}
