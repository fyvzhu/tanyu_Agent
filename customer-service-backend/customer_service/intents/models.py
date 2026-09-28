"""
Intent 模型定义
根据 01_slice_foundation 文档 #18-21 定义
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from customer_service.tasking.models import BusinessIntent, ActionMode


class IntentDecision(str, Enum):
    """Intent 决策结果"""
    ACCEPT = "accept"
    CLARIFY = "clarify"
    MULTIPLE_INTENTS = "multiple_intents"  # P1-21: top1 和 top2 分数太接近
    OUT_OF_SCOPE = "out_of_scope"
    CLASSIFIER_FAILURE = "classifier_failure"


class IntentFallbackReason(str, Enum):
    """Intent 回退原因"""
    LOW_CONFIDENCE = "low_confidence"
    OUT_OF_SCOPE = "out_of_scope"
    CLASSIFIER_FAILURE = "classifier_failure"
    MULTIPLE_INTENTS = "multiple_intents"


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
