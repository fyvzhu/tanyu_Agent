"""
Chat Session 和 Message 数据库模型
"""
from datetime import datetime
from typing import Optional
from uuid import uuid4
from sqlalchemy import String, Integer, DateTime, Text, Index, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from customer_service.models.base import Base
import enum


class MessageRole(str, enum.Enum):
    """消息角色枚举"""
    USER = "user"
    ASSISTANT = "assistant"


class ChatSession(Base):
    """
    Chat Session 模型
    - 每个 session 属于一个用户（user_id）
    - 支持 metadata 存储额外信息
    """
    __tablename__ = "chat_sessions"
    
    # 主键
    id: Mapped[str] = mapped_column(String(64), primary_key=True, comment="Session ID (UUID)")
    
    # 用户信息
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="用户 ID")
    channel: Mapped[str] = mapped_column(String(32), nullable=False, default="web", comment="渠道")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", comment="active/closed")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=datetime.utcnow, 
        nullable=False,
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
        comment="最后更新时间"
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="最后活跃时间"
    )
    
    # 元数据（可选，存储 JSON）
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Session 元数据 (JSON)"
    )
    
    # 关系
    messages: Mapped[list["ChatMessage"]] = relationship(
        "ChatMessage",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at"
    )
    
    # 索引
    __table_args__ = (
        Index("idx_user_last_active", "user_id", "last_active_at"),
    )


class ChatMessage(Base):
    """
    Chat Message 模型
    - 每条消息属于一个 session
    - 按时间顺序存储
    """
    __tablename__ = "chat_messages"
    
    # 主键
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="消息 ID")
    message_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        default=lambda: str(uuid4()),
        comment="公开 Message ID"
    )
    
    # Session 关联
    session_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="所属 Session ID"
    )
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, default="", index=True, comment="用户 ID")
    turn_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default=lambda: str(uuid4()),
        comment="Turn ID"
    )
    
    # 消息内容
    role: Mapped[str] = mapped_column(
        SQLEnum(MessageRole),
        nullable=False,
        comment="消息角色"
    )
    content: Mapped[str] = mapped_column(Text, nullable=False, comment="消息内容")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
        comment="创建时间"
    )
    
    # 元数据（可选，存储工具调用、Token 统计等）
    metadata_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="消息元数据 (JSON)"
    )
    objects_json: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="Chat objects JSON"
    )
    
    # 关系
    session: Mapped["ChatSession"] = relationship("ChatSession", back_populates="messages")
    
    # 索引
    __table_args__ = (
        Index("idx_session_created_message", "session_id", "created_at", "message_id"),
        Index("idx_user_session", "user_id", "session_id"),
    )
