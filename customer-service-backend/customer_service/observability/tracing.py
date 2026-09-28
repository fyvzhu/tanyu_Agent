"""
Langfuse 可观测性 - Fail-Open 模式
如果 Langfuse 不可用，自动降级为 NoopTracingService
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import Any

from customer_service.config.config import settings

logger = logging.getLogger(__name__)


class TracingService(ABC):
    """可观测性服务抽象接口"""

    @abstractmethod
    @asynccontextmanager
    async def span(self, name: str, **kwargs):
        """创建一个追踪 Span"""
        yield

    @abstractmethod
    def trace(self, name: str, **kwargs) -> Any:
        """创建一个追踪 Trace"""
        pass

    @abstractmethod
    def update_span(self, span: Any, **kwargs) -> None:
        """更新 Span 属性"""
        pass


class NoopTracingService(TracingService):
    """空操作追踪服务（降级方案）"""

    @asynccontextmanager
    async def span(self, name: str, **kwargs):
        """不执行任何操作"""
        yield NoopSpan()

    def trace(self, name: str, **kwargs) -> Any:
        """不执行任何操作"""
        return NoopTrace()

    def update_span(self, span: Any, **kwargs) -> None:
        """不执行任何操作"""
        pass


class NoopSpan:
    """空 Span 对象"""

    def update(self, **kwargs) -> None:
        pass


class NoopTrace:
    """空 Trace 对象"""

    def update(self, **kwargs) -> None:
        pass


class LangfuseTracingService(TracingService):
    """Langfuse 追踪服务（生产实现）"""

    def __init__(self):
        try:
            from langfuse import Langfuse

            self.client = Langfuse(
                public_key=settings.langfuse_public_key,
                secret_key=settings.langfuse_secret_key,
                host=settings.langfuse_host,
            )
            logger.info(f"Langfuse 客户端初始化成功: {settings.langfuse_host}")
        except Exception as e:
            logger.error(f"Langfuse 初始化失败: {e}")
            raise

    @asynccontextmanager
    async def span(self, name: str, **kwargs):
        """创建 Langfuse Span"""
        try:
            span = self.client.span(name=name, **kwargs)
            yield span
        except Exception as e:
            logger.warning(f"Langfuse span 创建失败: {e}")
            yield NoopSpan()

    def trace(self, name: str, **kwargs) -> Any:
        """创建 Langfuse Trace"""
        try:
            return self.client.trace(name=name, **kwargs)
        except Exception as e:
            logger.warning(f"Langfuse trace 创建失败: {e}")
            return NoopTrace()

    def update_span(self, span: Any, **kwargs) -> None:
        """更新 Span"""
        try:
            if hasattr(span, "update"):
                span.update(**kwargs)
        except Exception as e:
            logger.warning(f"Langfuse span 更新失败: {e}")


# 全局追踪服务实例
_tracing_service: TracingService | None = None


def get_tracing_service() -> TracingService:
    """
    获取追踪服务（Fail-Open 模式）
    - 如果 Langfuse 启用且初始化成功，返回 LangfuseTracingService
    - 否则返回 NoopTracingService（不影响业务）
    """
    global _tracing_service

    if _tracing_service is None:
        if settings.langfuse_enabled:
            try:
                _tracing_service = LangfuseTracingService()
                logger.info("使用 LangfuseTracingService")
            except Exception as e:
                logger.warning(f"Langfuse 初始化失败，降级为 NoopTracingService: {e}")
                _tracing_service = NoopTracingService()
        else:
            logger.info("Langfuse 未启用，使用 NoopTracingService")
            _tracing_service = NoopTracingService()

    return _tracing_service


# 向后兼容的别名
class Tracer:
    """向后兼容的 Tracer 类"""

    @asynccontextmanager
    async def span(self, name: str, **kwargs):
        service = get_tracing_service()
        async with service.span(name, **kwargs) as s:
            yield s
