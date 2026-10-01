"""
认证相关 Schemas
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class UserLoginRequest(BaseModel):
    """用户登录请求（简化版：只支持 username）"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class LoginRequest(BaseModel):
    """登录请求（兼容别名）"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int = Field(..., description="过期时间（秒）")
    user: "UserBasicInfo"


class UserBasicInfo(BaseModel):
    """用户基础信息"""
    user_id: str
    username: str
    nickname: str
    level: str
    phone_number_masked: str | None = None
    email_masked: str | None = None

    class Config:
        from_attributes = True


class RefreshTokenRequest(BaseModel):
    """刷新 Token 请求"""
    refresh_token: str | None = None  # 可从 cookie 读取


class UserRegisterRequest(BaseModel):
    """用户注册请求"""
    username: str = Field(..., min_length=4, max_length=20, description="用户名（4-20个字符，字母数字下划线）")
    nickname: str = Field(..., min_length=2, max_length=50, description="昵称")
    password: str = Field(..., min_length=8, max_length=16, description="密码（8-16个字符）")
    confirm_password: str = Field(..., min_length=8, max_length=16, description="确认密码")
