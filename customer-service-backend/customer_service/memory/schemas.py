"""
Memory 数据模型定义
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MemoryType(str, Enum):
    """记忆类型"""
    PREFERENCE = "preference"  # 偏好（颜色、品牌、风格等）
    CONSTRAINT = "constraint"  # 约束（预算、尺码等）
    DECISION = "decision"  # 决策记录
    CONTEXT = "context"  # 上下文信息
    MEASUREMENT = "measurement"  # 身材数据


class MemorySource(str, Enum):
    """记忆来源"""
    EXPLICIT = "explicit"  # 用户明确表达
    INFERRED = "inferred"  # 从对话推断
    ORDER_HISTORY = "order_history"  # 订单历史分析
    TOOL_RESULT = "tool_result"  # 工具调用结果


class MemoryStatus(str, Enum):
    """记忆状态"""
    ACTIVE = "active"  # 活跃
    SUPERSEDED = "superseded"  # 被新记忆取代
    DELETED = "deleted"  # 已删除


class ConflictAction(str, Enum):
    """冲突处理动作"""
    NEW = "new"  # 新增
    UPDATE = "update"  # 更新
    DUPLICATE = "duplicate"  # 重复跳过
    LOW_CONFIDENCE = "low_confidence"  # 低置信度，不写长期


class MemoryFact(BaseModel):
    """记忆事实（存储在 user_memory_facts 表）"""
    memory_id: str
    user_id: str
    memory_type: MemoryType
    memory_key: str | None = None  # 例如 "preferred_color"
    memory_text: str  # 自然语言描述
    value_json: dict[str, Any] | None = None  # 结构化值
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    source: MemorySource = MemorySource.EXPLICIT
    source_session_id: str | None = None
    source_turn_id: str | None = None
    status: MemoryStatus = MemoryStatus.ACTIVE
    expires_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class MemoryEvent(BaseModel):
    """记忆变更事件（audit log）"""
    id: int | None = None
    memory_id: str
    action: str  # create / update / supersede / delete
    old_value_json: dict[str, Any] | None = None
    new_value_json: dict[str, Any] | None = None
    source_turn_id: str | None = None
    created_at: datetime


class UserPreference(BaseModel):
    """用户偏好"""
    id: int | None = None
    user_id: str
    preference_type: str  # color / brand / category / style / usage / fit
    preference_value: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: MemorySource = MemorySource.EXPLICIT
    active: bool = True
    created_at: datetime
    updated_at: datetime


class UserMeasurement(BaseModel):
    """用户身材数据"""
    id: int | None = None
    user_id: str
    height_cm: float | None = None
    weight_kg: float | None = None
    bust_cm: float | None = None
    waist_cm: float | None = None
    hip_cm: float | None = None
    shoulder_cm: float | None = None
    foot_length_cm: float | None = None
    foot_width_cm: float | None = None
    source: MemorySource = MemorySource.EXPLICIT
    updated_at: datetime


class MemoryCandidate(BaseModel):
    """待持久化的记忆候选"""
    memory_text: str
    memory_type: MemoryType
    memory_key: str | None = None
    value_json: dict[str, Any] | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    importance: float = Field(ge=0.0, le=1.0)
    source: MemorySource = MemorySource.EXPLICIT
    source_session_id: str | None = None
    source_turn_id: str | None = None


class SemanticMemoryPayload(BaseModel):
    """Qdrant payload 结构"""
    memory_id: str
    user_id: str
    memory_type: str
    memory_key: str | None = None
    memory_text: str
    importance: float
    confidence: float
    source_session_id: str | None = None
    source_turn_id: str | None = None
    status: str
    created_at: str
    expires_at: str | None = None
