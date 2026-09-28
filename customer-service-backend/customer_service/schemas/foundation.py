"""
Foundation 核心共享 Schema
根据 01_slice_foundation 文档 #13.1 定义

这些是本项目 Runtime Contract 的正式最小定义

注意：
- ToolResult, ToolError, EvidenceItem 等工具相关类型统一定义在 customer_service/tools/models.py
- 本文件只保留 Session、Confirmation 等非工具类型
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ==================== Session User Context ====================
class SessionUserContext(BaseModel):
    """Session 级用户上下文 - 仅保存 measurement override"""
    measurement_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Session 级 measurement 覆盖值"
    )
    confirmed_measurement_fields: set[str] = Field(
        default_factory=set,
        description="已确认的 measurement 字段"
    )


# ==================== Confirmation ====================
class ConfirmationKind(str, Enum):
    """确认类型枚举"""
    EXECUTE_RETURN = "execute_return"
    EXECUTE_EXCHANGE = "execute_exchange"
    CONFIRM_STORED_MEASUREMENTS = "confirm_stored_measurements"
    SAVE_MEASUREMENTS = "save_measurements"


class PendingConfirmation(BaseModel):
    """待确认项 - 只存在于 TaskFrame.pending_confirmation"""
    kind: ConfirmationKind = Field(..., description="确认类型")
    payload: dict[str, Any] = Field(default_factory=dict, description="确认相关数据")
    created_turn_id: str = Field(..., description="创建该确认的 Turn ID")
