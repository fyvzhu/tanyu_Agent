"""
刷新令牌会话模型
用于存储和管理用户的刷新令牌
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Integer, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RefreshTokenSession(Base):
    """刷新令牌会话表"""
    __tablename__ = "refresh_token_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(64), 
        ForeignKey("users.user_id", ondelete="CASCADE"), 
        nullable=False,
        index=True,
        comment="关联users.user_id"
    )
    token_hash: Mapped[str] = mapped_column(
        String(64), 
        nullable=False, 
        unique=True,
        index=True,
        comment="刷新令牌的SHA-256哈希值"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False,
        comment="令牌过期时间"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, 
        nullable=False, 
        default=datetime.now,
        comment="令牌创建时间"
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime, 
        nullable=True,
        comment="令牌撤销时间"
    )

    # 关联关系
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])

    # 复合索引：用于查询用户的活跃会话
    __table_args__ = (
        Index('idx_user_expires', 'user_id', 'expires_at'),
    )
