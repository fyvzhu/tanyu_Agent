"""
异常定义模块
"""
from __future__ import annotations


class AppException(Exception):
    """应用基础异常"""
    def __init__(self, message: str, code: str = "APP_ERROR", status_code: int = 500):
        self.message = message
        self.code = code
        self.status_code = status_code
        super().__init__(self.message)


class AuthenticationError(AppException):
    """认证失败异常"""
    def __init__(self, message: str = "认证失败"):
        super().__init__(message, code="AUTH_REQUIRED", status_code=401)


class InvalidCredentialsError(AppException):
    """无效凭证异常"""
    def __init__(self, message: str = "用户名或密码错误"):
        super().__init__(message, code="INVALID_CREDENTIALS", status_code=401)


class TokenExpiredError(AppException):
    """Token过期异常"""
    def __init__(self, message: str = "Token已过期"):
        super().__init__(message, code="TOKEN_EXPIRED", status_code=401)


class AccountLockedError(AppException):
    """账号锁定异常"""
    def __init__(self, message: str = "账号已被锁定"):
        super().__init__(message, code="ACCOUNT_LOCKED", status_code=403)


class PermissionDeniedError(AppException):
    """权限拒绝异常"""
    def __init__(self, message: str = "无权访问该资源"):
        super().__init__(message, code="FORBIDDEN", status_code=403)


class ValidationError(AppException):
    """数据验证异常"""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(message, code="VALIDATION_ERROR", status_code=422)
        self.details = details or {}


class ResourceNotFoundError(AppException):
    """资源不存在异常"""
    def __init__(self, message: str = "资源不存在"):
        super().__init__(message, code="RESOURCE_NOT_FOUND", status_code=404)


class ConflictError(AppException):
    """资源冲突异常"""
    def __init__(self, message: str = "资源冲突"):
        super().__init__(message, code="CONFLICT", status_code=409)


class BusinessRuleError(AppException):
    """业务规则异常"""
    def __init__(self, message: str):
        super().__init__(message, code="BUSINESS_RULE_VIOLATION", status_code=422)


class RateLimitError(AppException):
    """请求限流异常"""
    def __init__(self, message: str = "请求过于频繁"):
        super().__init__(message, code="RATE_LIMITED", status_code=429)


class UpstreamTimeoutError(AppException):
    """上游服务超时异常"""
    def __init__(self, message: str = "上游服务超时"):
        super().__init__(message, code="UPSTREAM_TIMEOUT", status_code=504)


class UpstreamUnavailableError(AppException):
    """上游服务不可用异常"""
    def __init__(self, message: str = "上游服务不可用"):
        super().__init__(message, code="UPSTREAM_UNAVAILABLE", status_code=503)
