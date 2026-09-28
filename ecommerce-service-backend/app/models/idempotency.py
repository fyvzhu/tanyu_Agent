"""
幂等性记录模型
用于防止重复请求处理
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class IdempotencyRecord(Base):
    """幂等性记录表"""
    __tablename__ = "idempotency_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(255), 
        nullable=False, 
        unique=True,
        index=True,
        comment="幂等性键"
    )
    user_id: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="用户ID"
    )
    request_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="请求路径"
    )
    request_method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="请求方法"
    )
    response_status: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="响应状态码"
    )
    response_body: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="响应体内容"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.now,
        comment="创建时间"
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        comment="过期时间"
    )
