"""
Request-ID 中间件
根据 07 API Runtime Contract 要求实现 Request-ID 传播

P1-50 修复：实现 Request-ID 的 HTTP 契约
- 从请求头读取或生成 Request-ID
- 在响应头中回写 Request-ID
- 存储在 request.state 中供后续使用
"""
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Request-ID 中间件
    
    功能：
    1. 从请求头读取 X-Request-ID（大小写不敏感）
    2. 如果没有则生成一个新的 UUID
    3. 存储在 request.state.request_id 中供后续使用
    4. 在响应头中回写 X-Request-ID
    """
    
    async def dispatch(self, request: Request, call_next):
        # 读取或生成 Request-ID（支持大小写不敏感）
        request_id = request.headers.get("X-Request-ID") or request.headers.get("x-request-id")
        if not request_id:
            request_id = str(uuid.uuid4())
        
        # 存储在 request.state 中供后续使用
        request.state.request_id = request_id
        
        # 处理请求
        response = await call_next(request)
        
        # 在响应头中回写 Request-ID
        response.headers["X-Request-ID"] = request_id
        
        return response
