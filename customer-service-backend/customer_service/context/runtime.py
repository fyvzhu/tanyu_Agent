"""
AgentRuntimeContext: Runtime-only 上下文
根据 01_slice_foundation 文档 #7 定义

禁止进入：
- LangGraph persistent state
- Prompt
- Memory
- Qdrant
- Langfuse raw payload
- ToolResult
"""
from pydantic import BaseModel, Field, SecretStr
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import core_schema

from .principal import AuthPrincipal


class AgentRuntimeContext(BaseModel):
    """
    Agent 运行时上下文 - 仅在请求期间有效

    禁止持久化到：
    - LangGraph state
    - Prompt
    - Memory
    - 向量数据库
    - 可观测性平台原始负载
    """
    principal: AuthPrincipal = Field(..., description="认证主体")
    request_id: str = Field(..., description="请求追踪ID")
    session_id: str = Field(..., description="Chat Session ID")
    turn_id: str | None = Field(None, description="当前 Turn ID")
    request_deadline_monotonic: float = Field(..., description="请求截止时间（单调时钟）")
    user_access_token: SecretStr = Field(..., description="用户 Access Token（敏感信息）")
