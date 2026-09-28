from __future__ import annotations

from pydantic import BaseModel, Field


class ToolError(BaseModel):
    code: str
    message: str
    safe_message: str
    retryable: bool = False
    details: dict = Field(default_factory=dict)


class ToolExecutionError(Exception):
    def __init__(self, error: ToolError):
        super().__init__(error.message)
        self.error = error
