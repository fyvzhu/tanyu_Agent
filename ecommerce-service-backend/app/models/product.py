"""
商品体系数据模型
包含3张表：products, product_skus, promotions
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Product(Base):
    """商品SPU信息表（SPU/SKU分层设计）"""
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="商品ID: 15970")
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="品牌", index=True)
    product_display_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="商品展示名称")
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="性别: 男士/女士/男童/女童")
    master_category: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="主分类: 服装/鞋靴", index=True)
    sub_category: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="子分类: 上装/下装", index=True)
    type: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="类型: 衬衫/牛仔裤")
    season: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="季节")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True, comment="年份")
    usage: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="用途: 休闲/正式/运动")
    material: Mapped[str | None] = mapped_column(Text, nullable=True, comment="材质描述")
    selling_points: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="卖点JSON数组")
    size_data: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="尺码表JSON")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    # 关联关系
    skus: Mapped[list["ProductSKU"]] = relationship(back_populates="product", cascade="all, delete-orphan")
    promotions: Mapped[list["Promotion"]] = relationship(back_populates="product", cascade="all, delete-orphan")


class ProductSKU(Base):
    """商品SKU信息表（价格/库存/颜色/尺码）"""
    __tablename__ = "product_skus"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sku_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="SKU15970_01")
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True, comment="关联products.product_id")
    color: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="颜色")
    size_code: Mapped[str | None] = mapped_column(String(50), nullable=True, comment="尺码代码: S/M/L/40/41")
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, comment="价格")
    stock_status: Mapped[str] = mapped_column(String(32), nullable=False, comment="in_stock/out_of_stock")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    # 关联关系
    product: Mapped["Product"] = relationship(back_populates="skus")


class Promotion(Base):
    """促销信息表"""
    __tablename__ = "promotions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promotion_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="PROMO20260001")
    product_id: Mapped[str] = mapped_column(String(64), ForeignKey("products.product_id", ondelete="CASCADE"), nullable=False, index=True, comment="关联商品")
    promotion_name: Mapped[str] = mapped_column(String(255), nullable=False, comment="促销名称")
    promotion_type: Mapped[str] = mapped_column(String(50), nullable=False, comment="percentage_discount/fixed_discount/threshold_discount/member_price")
    threshold_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, comment="满减门槛")
    discount_amount: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, comment="减免金额")
    discount_rate: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="折扣率")
    promo_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, comment="会员专享价")
    member_level: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="会员等级限制: ALL/PLUS")
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="开始时间", index=True)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="结束时间", index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, comment="active/scheduled/expired", index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True, comment="促销描述")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    product: Mapped["Product"] = relationship(back_populates="promotions")
