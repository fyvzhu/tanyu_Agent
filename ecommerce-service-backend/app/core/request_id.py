"""
Request-ID 中间件
用于追踪请求链路，支持分布式追踪
"""
from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Request-ID 中间件：读取或生成 X-Request-ID"""
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # 1. 从请求头读取 X-Request-ID，如果没有则生成新的
        request_id = request.headers.get("X-Request-ID")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # 2. 将 request_id 存储到 request.state 中，供后续使用
        request.state.request_id = request_id
        
        # 3. 调用下一个处理器
        response = await call_next(request)
        
        # 4. 在响应头中回写 X-Request-ID
        response.headers["X-Request-ID"] = request_id
        
        return response


def get_request_id(request: Request) -> str:
    """从请求中获取 request_id"""
    return getattr(request.state, "request_id", "unknown")
