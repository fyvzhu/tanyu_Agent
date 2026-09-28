"""
Task 模型定义
根据 01_slice_foundation 文档 #15 定义
"""
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from customer_service.schemas.foundation import PendingConfirmation


class TaskStatus(str, Enum):
    """Task 状态枚举"""
    ACTIVE = "active"
    WAITING_SLOT = "waiting_slot"
    WAITING_CONFIRMATION = "waiting_confirmation"
    READY = "ready"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELED = "canceled"
    FAILED = "failed"


class ActionMode(str, Enum):
    """行动模式枚举"""
    INFORMATIONAL = "informational"
    ACTION_REQUEST = "action_request"


class BusinessIntent(str, Enum):
    """9 个业务意图枚举 - 全局固定"""
    PRODUCT_QUERY = "product_query"
    SIZE_RECOMMEND = "size_recommend"
    URGE_ORDER_PAYMENT = "urge_order_payment"
    PROMOTION_QUERY = "promotion_query"
    LOGISTICS_QUERY = "logistics_query"
    RETURN = "return"
    EXCHANGE = "exchange"
    CHITCHAT = "chitchat"
    URGE_SHIPPING = "urge_shipping"


class TaskFrame(BaseModel):
    """
    Task 帧 - 单个任务的完整状态

    固定约束：
    - pending_confirmation 只存在 TaskFrame 中，不在 AgentState 顶层
    """
    task_id: str = Field(..., description="Task 唯一ID")
    intent: BusinessIntent = Field(..., description="业务意图")
    status: TaskStatus = Field(..., description="任务状态")
    slots: dict[str, Any] = Field(default_factory=dict, description="槽位数据")
    missing_slots: list[str] = Field(default_factory=list, description="缺失的槽位")
    action_mode: ActionMode | None = Field(None, description="行动模式")
    side_effect: bool = Field(False, description="是否有副作用")
    execute_confirmed: bool = Field(False, description="是否已确认执行")
    pending_confirmation: PendingConfirmation | None = Field(
        None,
        description="待确认项（只存在这里）"
    )
    paused_from_status: TaskStatus | None = Field(None, description="暂停前的状态")
    pause_reason: str | None = Field(None, description="暂停原因")
    created_turn_id: str = Field(..., description="创建该任务的 Turn ID")
    last_turn_id: str = Field(..., description="最后一次操作的 Turn ID")


class FocusRef(BaseModel):
    """
    会话焦点引用 - 全局唯一指代对象

    只保留一个全局指代对象，不要同时维护多份
    """
    entity_type: Literal["product", "order"] = Field(..., description="实体类型")
    entity_id: str = Field(..., description="实体ID")


class PendingIntentSelection(BaseModel):
    """待选择的多个 Intent"""
    candidate_intents: list[BusinessIntent] = Field(..., description="候选 Intent 列表")
    original_turn_id: str = Field(..., description="产生多 Intent 的 Turn ID")
