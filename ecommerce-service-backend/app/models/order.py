"""
订单体系数据模型
包含4张表：orders, order_items, logistics_records, logistics_traces
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Order(Base):
    """订单主表"""
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="O20260913000016")
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False, index=True, comment="关联users.user_id")
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True, comment="待付款/待发货/运输中/待收货/已完成")
    status_desc: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="状态描述")
    amount: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="订单总金额")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    receiver_name: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="收货人姓名")
    receiver_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="收货人电话")
    receiver_address: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="收货地址")

    # 关联关系
    user: Mapped["User"] = relationship()
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    logistics_records: Mapped[list["LogisticsRecord"]] = relationship(back_populates="order", cascade="all, delete-orphan")
    return_requests: Mapped[list["ReturnRequest"]] = relationship(back_populates="order")
    exchange_requests: Mapped[list["ExchangeRequest"]] = relationship(back_populates="order")
    shipping_urge_requests: Mapped[list["ShippingUrgeRequest"]] = relationship(back_populates="order")


class OrderItem(Base):
    """订单明细表（退款金额计算依据）"""
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, index=True, comment="关联orders.order_id")
    product_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="商品ID")
    sku_id: Mapped[str] = mapped_column(String(64), nullable=False, comment="SKU ID")
    quantity: Mapped[int] = mapped_column(Integer, nullable=False, comment="数量")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="单价（下单时快照）")

    # 关联关系
    order: Mapped["Order"] = relationship(back_populates="items")


class LogisticsRecord(Base):
    """物流记录表"""
    __tablename__ = "logistics_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[str] = mapped_column(String(64), ForeignKey("orders.order_id", ondelete="CASCADE"), nullable=False, index=True, comment="关联orders.order_id")
    logistics_company: Mapped[str] = mapped_column(String(100), nullable=False, comment="物流公司")
    tracking_number: Mapped[str] = mapped_column(String(100), nullable=False, comment="运单号")
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="物流状态")
    status_desc: Mapped[str | None] = mapped_column(String(255), nullable=True, comment="状态描述")
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    order: Mapped["Order"] = relationship(back_populates="logistics_records")
    traces: Mapped[list["LogisticsTrace"]] = relationship(back_populates="record", cascade="all, delete-orphan")


class LogisticsTrace(Base):
    """物流轨迹表"""
    __tablename__ = "logistics_traces"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    logistics_record_id: Mapped[int] = mapped_column(Integer, ForeignKey("logistics_records.id", ondelete="CASCADE"), nullable=False, index=True, comment="关联logistics_records.id")
    trace_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="轨迹时间")
    trace_desc: Mapped[str] = mapped_column(String(500), nullable=False, comment="轨迹描述")

    # 关联关系
    record: Mapped["LogisticsRecord"] = relationship(back_populates="traces")
