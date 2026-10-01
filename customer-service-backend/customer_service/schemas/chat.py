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


class ProductCard(BaseModel):
    """
    商品卡片对象（出站格式）

    问题修复2：按照 v7 Slice02 规范定义扁平商品卡结构
    """
    type: Literal["product_card"] = "product_card"
    product_id: str
    title: str
    brand: str | None = None
    main_image_url: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    selected_sku_id: str | None = None
    selected_sku_price: float | None = None
    stock_status: str | None = None


class PromotionCard(BaseModel):
    """
    促销卡片对象（出站格式）

    问题修复2：明确定义促销卡结构，与 Commerce API 字段对齐
    """
    type: Literal["promotion"] = "promotion"
    promotion_id: str
    title: str  # Commerce API 返回字段名
    promotion_type: str
    description: str | None = None
    start_at: str | None = None  # ISO 8601 datetime string
    end_at: str | None = None
    applicable: bool | None = None

    # 促销参数（根据类型不同而不同）
    discount_rate: float | None = None  # percentage_discount 使用
    discount_amount: float | None = None  # fixed_discount 和 threshold_discount 使用
    threshold_amount: float | None = None  # threshold_discount 使用（原 min_purchase）
    promo_price: float | None = None  # member_price 使用

    # 向后兼容字段
    promotion_name: str | None = None  # 别名，指向 title


# 问题修复2: ChatObject 使用联合类型，明确区分对象类型
ChatObject = ProductCard | PromotionCard


class ChatTaskSummary(BaseModel):
    intent: str | None = None
    status: str | None = None


class ChatTurnResponse(BaseModel):
    turn_id: str
    message_id: str
    text: str
    objects: list[dict[str, Any]] = Field(default_factory=list)  # 问题修复2: 使用 dict 避免序列化问题
    task: ChatTaskSummary
    dialogue_reason: str | None = None
    retrieved_context: dict[str, Any] | None = None  # RAG 检索上下文


class ChatHistoryItem(BaseModel):
    turn_id: str
    role: Literal["user", "assistant"]
    message_id: str
    content: str
    created_at: str
    objects: list[dict[str, Any]] = Field(default_factory=list)  # 问题修复2: 使用 dict 避免序列化问题


class ChatHistoryResponse(BaseModel):
    """
    聊天历史响应

    P1-34 修复：实现 cursor pagination
    - messages: 消息列表
    - next_cursor: 下一页游标，None 表示没有更多数据
    """
    messages: list[ChatHistoryItem]
    next_cursor: str | None = Field(None, description="下一页游标，None 表示没有更多数据")
