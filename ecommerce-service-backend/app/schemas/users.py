"""
用户相关 Schemas
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class UserProfileResponse(BaseModel):
    """用户基础资料响应"""
    user_id: str
    username: str
    nickname: str
    phone_number_masked: str | None
    email_masked: str | None
    level: str

    class Config:
        from_attributes = True


class UpdateProfileRequest(BaseModel):
    """更新用户基础资料请求"""
    nickname: str | None = None
    phone_number: str | None = None
    email: str | None = None


# 别名，用于 API 层
UserProfileUpdateRequest = UpdateProfileRequest


class UserProfileDetailResponse(BaseModel):
    """用户详细资料响应（包含头像、性别、生日等）"""
    user_id: str
    avatar_url: str | None
    bio: str | None
    gender: str | None
    birth_date: date | None

    class Config:
        from_attributes = True


class UserProfileDetailUpdate(BaseModel):
    """更新用户详细资料请求"""
    avatar_url: str | None = None
    bio: str | None = None
    gender: str | None = None
    birth_date: date | None = None


class UserPreferencesResponse(BaseModel):
    """用户偏好响应"""
    user_id: str
    preferred_categories: list[str] | None
    preferred_colors: list[str] | None
    preferred_styles: list[str] | None
    size_preference: str | None
    price_range_min: float | None
    price_range_max: float | None

    class Config:
        from_attributes = True


class UserPreferencesUpdate(BaseModel):
    """更新用户偏好请求"""
    preferred_categories: list[str] | None = None
    preferred_colors: list[str] | None = None
    preferred_styles: list[str] | None = None
    size_preference: str | None = None
    price_range_min: float | None = None
    price_range_max: float | None = None


class UserPreferenceItem(BaseModel):
    """用户偏好项（旧版兼容）"""
    preference_type: str = Field(..., description="color/style/budget等")
    preference_value: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: str = Field(default="explicit", description="explicit/implicit")


class UserMeasurementsRequest(BaseModel):
    """用户体型数据请求"""
    height_cm: Decimal | None = Field(None, ge=0, le=300, description="身高(cm)")
    weight_kg: Decimal | None = Field(None, ge=0, le=500, description="体重(kg)")
    bust_cm: Decimal | None = Field(None, ge=0, le=300, description="胸围(cm)")
    waist_cm: Decimal | None = Field(None, ge=0, le=300, description="腰围(cm)")
    hip_cm: Decimal | None = Field(None, ge=0, le=300, description="臀围(cm)")
    shoulder_cm: Decimal | None = Field(None, ge=0, le=100, description="肩宽(cm)")
    foot_length_cm: Decimal | None = Field(None, ge=0, le=50, description="脚长(cm)")
    foot_width_cm: Decimal | None = Field(None, ge=0, le=30, description="脚宽(cm)")


# 别名，用于 API 层
UserMeasurementsUpdateRequest = UserMeasurementsRequest
UserMeasurementsPatch = UserMeasurementsRequest


class UserMeasurementsResponse(BaseModel):
    """用户体型数据响应"""
    user_id: str
    height_cm: Decimal | None
    weight_kg: Decimal | None
    bust_cm: Decimal | None
    waist_cm: Decimal | None
    hip_cm: Decimal | None
    shoulder_cm: Decimal | None
    foot_length_cm: Decimal | None
    foot_width_cm: Decimal | None
    updated_at: str | None

    class Config:
        from_attributes = True
