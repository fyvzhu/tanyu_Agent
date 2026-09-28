from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceItem(BaseModel):
    source_type: Literal["commerce_api", "rag", "memory", "derived"]
    source_name: str
    reference_id: str | None = None
    facts: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolError(BaseModel):
    code: str
    message: str
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    tool_name: str
    ok: bool
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    error: ToolError | None = None
    side_effect: bool = False


class RetryPolicy(str, Enum):
    NONE = "none"
    READ_ONCE_RETRY = "read_once_retry"
    WRITE_SAME_IDEMPOTENCY_KEY = "write_same_idempotency_key"

