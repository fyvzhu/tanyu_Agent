"""
Flow 层统一数据模型

根据 v7 Foundation #22 IntentPolicy 与 IntentFlowRegistry 接口定义

P0 修复：
- IntentFlow 协议必须包含 runtime 参数
- 确保所有 Flow 实现符合统一签名
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from pydantic import BaseModel, Field

from customer_service.tools.models import ToolResult

if TYPE_CHECKING:
    from customer_service.graph.state import AgentState
    from customer_service.context.runtime import AgentRuntimeContext


class FlowResult(BaseModel):
    """
    Flow 执行结果的统一契约

    v7 #22 要求：
    - ready_for_response: 是否已准备好生成响应（False 表示需要补槽或等待）
    - tool_result: 工具执行结果（可能为 None）
    - dialogue_reason: 对话状态原因（如 "waiting_slot", "clarify", "error"）
    - objects: 业务对象列表（商品、订单、促销等）
    """
    ready_for_response: bool
    tool_result: ToolResult | None = None
    dialogue_reason: str | None = None
    objects: list[dict[str, Any]] = Field(default_factory=list)


class ConversionEvidence(BaseModel):
    """
    转化证据 - 催拍催付所需的真实商品证据

    P1-30 修复：使用 Pydantic Model 替代 dict，避免字段拼错、缺失、任意 get() 等问题
    """
    product_id: str = Field(..., description="商品ID")
    product_name: str | None = Field(None, description="商品名称")
    product_selling_points: list[str] = Field(default_factory=list, description="商品卖点")
    verified_material: str | None = Field(None, description="验证的材质信息")
    user_need: list[str] = Field(default_factory=list, description="用户需求")
    hesitation_signals: list[str] = Field(default_factory=list, description="犹豫信号")
    current_promotions: list[dict[str, Any]] = Field(default_factory=list, description="当前促销")
    explicit_preferences: dict[str, Any] = Field(default_factory=dict, description="明确偏好")
    relevant_memories: list[dict[str, Any]] = Field(default_factory=list, description="相关记忆")
    verified_stock_summary: dict[str, Any] | None = Field(None, description="库存摘要")
    evidence_sources: list[dict[str, Any]] = Field(default_factory=list, description="证据来源")


class IntentFlow(Protocol):
    """
    Intent Flow 协议

    P0 修复：所有业务 Flow 必须实现此协议
    - state: AgentState（持久化状态）
    - runtime: AgentRuntimeContext（请求范围的运行时上下文）
    """
    async def execute(self, state: "AgentState", runtime: "AgentRuntimeContext") -> FlowResult:
        """
        执行 Flow 逻辑

        Args:
            state: Agent 状态（持久化字段）
            runtime: Runtime Context（user_id, session_id, user_access_token）

        Returns:
            FlowResult: 统一的执行结果
        """
        ...
