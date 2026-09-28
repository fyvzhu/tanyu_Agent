"""
用户体系数据模型
包含5张表：users, user_auth, user_measurements, user_profiles, user_preferences
"""
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal

from sqlalchemy import DateTime, Date, ForeignKey, Numeric, String, Text, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    """用户基础信息表"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True, comment="业务ID: U0001")
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True, comment="用户名")
    nickname: Mapped[str] = mapped_column(String(100), nullable=False, comment="昵称")
    phone_number: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="手机号")
    email: Mapped[str | None] = mapped_column(String(100), nullable=True, comment="邮箱")
    level: Mapped[str] = mapped_column(String(32), nullable=False, comment="会员等级: PLUS/普通会员")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)

    # 关联关系
    auth: Mapped["UserAuth"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    profile: Mapped["UserProfile"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    preferences: Mapped["UserPreferences"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    measurements: Mapped["UserMeasurements"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    orders: Mapped[list["Order"]] = relationship(back_populates="user")


class UserAuth(Base):
    """用户认证信息表（独立安全管理）"""
    __tablename__ = "user_auth"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True, comment="关联users.user_id")
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True, comment="登录用户名")
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False, comment="Argon2id加密密码")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", comment="active/locked")
    failed_login_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="失败登录次数")
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="锁定截止时间")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, comment="最后登录时间")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    user: Mapped["User"] = relationship(back_populates="auth")


class UserMeasurements(Base):
    """用户体型测量数据表（尺码推荐核心）"""
    __tablename__ = "user_measurements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True, comment="关联users.user_id")
    height_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="身高(cm)")
    weight_kg: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="体重(kg)")
    bust_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="胸围(cm)")
    waist_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="腰围(cm)")
    hip_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="臀围(cm)")
    shoulder_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="肩宽(cm)")
    foot_length_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="脚长(cm)")
    foot_width_cm: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True, comment="脚宽(cm)")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    user: Mapped["User"] = relationship(back_populates="measurements")


class UserProfile(Base):
    """用户资料扩展表（头像、简介、性别、生日）"""
    __tablename__ = "user_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True, comment="关联users.user_id")
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True, comment="头像URL")
    bio: Mapped[str | None] = mapped_column(Text, nullable=True, comment="个人简介")
    gender: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="性别: male/female/other")
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True, comment="生日")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    user: Mapped["User"] = relationship(back_populates="profile")


class UserPreferences(Base):
    """用户购物偏好表（品类、颜色、风格、价格区间）"""
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False, unique=True, comment="关联users.user_id")
    preferred_categories: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="偏好品类列表: [\"tops\", \"dresses\"]")
    preferred_colors: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="偏好颜色列表: [\"black\", \"white\"]")
    preferred_styles: Mapped[dict | None] = mapped_column(JSON, nullable=True, comment="偏好风格列表: [\"casual\", \"formal\"]")
    size_preference: Mapped[str | None] = mapped_column(String(32), nullable=True, comment="版型偏好: loose_fit/regular/tight_fit")
    price_range_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, comment="价格区间最小值")
    price_range_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True, comment="价格区间最大值")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, onupdate=datetime.now)

    # 关联关系
    user: Mapped["User"] = relationship(back_populates="preferences")
