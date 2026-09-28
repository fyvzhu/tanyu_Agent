from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel, Field


T = TypeVar("T")


class ErrorBody(BaseModel):
    code: str
    message: str
    safe_message: str
    details: dict = Field(default_factory=dict)


class ApiResponse(BaseModel, Generic[T]):
    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None
    request_id: str | None = None


def ok(data: T, request_id: str | None = None) -> ApiResponse[T]:
    return ApiResponse(success=True, data=data, request_id=request_id)
