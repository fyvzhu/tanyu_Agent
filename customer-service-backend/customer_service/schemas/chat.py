from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    channel: str = "web"


class CreateSessionResponse(BaseModel):
    session_id: str
    status: Literal["active", "closed"] = "active"
    channel: str = "web"
    created_at: str


class ChatMessageRequest(BaseModel):
    """
    聊天消息请求

    问题二修复：删除 focused_object 字段，使用 v7 规范的 conversation_focus
    客户端不再需要维护 focused_object 状态，由服务端 Agent 自动管理
    """
    message: str = Field(..., min_length=1, max_length=4000)
    client_context: dict[str, Any] = Field(default_factory=dict)


class ChatObject(BaseModel):
    type: str
    product: dict[str, Any] | None = None
    sku: dict[str, Any] | None = None
    assets: dict[str, Any] | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ChatTaskSummary(BaseModel):
    intent: str | None = None
    status: str | None = None


class ChatTurnResponse(BaseModel):
    turn_id: str
    message_id: str
    text: str
    objects: list[ChatObject] = Field(default_factory=list)
    task: ChatTaskSummary
    dialogue_reason: str | None = None
    retrieved_context: dict[str, Any] | None = None  # RAG 检索上下文


class ChatHistoryItem(BaseModel):
    turn_id: str
    role: Literal["user", "assistant"]
    message_id: str
    content: str
    created_at: str
    objects: list[ChatObject] = Field(default_factory=list)


class ChatHistoryResponse(BaseModel):
    """
    聊天历史响应

    P1-34 修复：实现 cursor pagination
    - messages: 消息列表
    - next_cursor: 下一页游标，None 表示没有更多数据
    """
    messages: list[ChatHistoryItem]
    next_cursor: str | None = Field(None, description="下一页游标，None 表示没有更多数据")
