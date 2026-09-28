"""
售后体系数据模型
包含3张表：return_requests, exchange_requests, shipping_urge_requests
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ReturnRequest(Base):
    """退货退款申请表"""
    __tablename__ = "return_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="RET-yyyymmdd-xxxxx")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="用户ID")
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id"), nullable=False, index=True, comment="订单ID")
    product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="商品ID")
    sku_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="SKU ID")
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment="退货原因")
    refund_amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="退款金额（系统计算）")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="REQUESTED/APPROVED/REJECTED/COMPLETED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    order: Mapped["Order"] = relationship(back_populates="return_requests")


class ExchangeRequest(Base):
    """换货申请表（同product_id换颜色/尺码）"""
    __tablename__ = "exchange_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="EXG-yyyymmdd-xxxxx")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="用户ID")
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id"), nullable=False, index=True, comment="订单ID")
    product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="商品ID")
    original_sku_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="原SKU ID")
    exchange_sku_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="目标SKU ID")
    reason: Mapped[str] = mapped_column(Text, nullable=False, comment="换货原因")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="REQUESTED/APPROVED/REJECTED/COMPLETED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    order: Mapped["Order"] = relationship(back_populates="exchange_requests")


class ShippingUrgeRequest(Base):
    """催发货申请表"""
    __tablename__ = "shipping_urge_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="URG-yyyymmdd-xxxxx")
    user_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True, comment="用户ID")
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id"), nullable=False, index=True, comment="订单ID")
    reason_code: Mapped[str] = mapped_column(String(32), nullable=False, comment="NORMAL_URGE/URGENT")
    reason_detail: Mapped[str | None] = mapped_column(Text, nullable=True, comment="详细原因")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="SUBMITTED/HANDLED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    # 关联关系
    order: Mapped["Order"] = relationship(back_populates="shipping_urge_requests")
