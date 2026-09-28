"""
AuthPrincipal: 用户身份唯一来源
根据 01_slice_foundation 文档 #7 定义
"""
from pydantic import BaseModel, ConfigDict, Field


class AuthPrincipal(BaseModel):
    """
    认证主体 - 唯一身份来源

    身份唯一来源：JWT.sub
    """
    model_config = ConfigDict(frozen=True)

    user_id: str = Field(..., description="用户ID，来自 JWT sub claim")
