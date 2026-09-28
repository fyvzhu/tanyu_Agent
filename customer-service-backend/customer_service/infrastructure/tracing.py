"""
Langfuse TracingService - Slice 01 Fail-Open 实现
提供 LLM 调用的可观测性追踪
"""
from __future__ import annotations

from typing import Any, Optional
from loguru import logger

from customer_service.config.config import settings


class TracingService:
    """
    Langfuse 追踪服务 - Fail-Open 模式
    
    当 Langfuse 不可用或配置错误时，不阻塞主流程，仅记录警告日志
    """

    def __init__(self, enabled: bool | None = None):
        self.enabled = enabled if enabled is not None else settings.langfuse_enabled
        self._langfuse = None
        
        if self.enabled:
            try:
                from langfuse import Langfuse
                self._langfuse = Langfuse(
                    public_key=getattr(settings, 'langfuse_public_key', None),
                    secret_key=getattr(settings, 'langfuse_secret_key', None),
                    host=getattr(settings, 'langfuse_host', None),
                )
                logger.info("[TracingService] ✅ Langfuse 初始化成功")
            except Exception as e:
                logger.warning(f"[TracingService] ⚠️ Langfuse 初始化失败（Fail-Open）: {e}")
                self.enabled = False

    def trace_llm_call(
        self,
        name: str,
        model: str,
        input_messages: list[dict[str, Any]],
        output_text: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        记录 LLM 调用追踪
        
        Fail-Open: 如果追踪失败，仅记录日志，不抛出异常
        """
        if not self.enabled or not self._langfuse:
            logger.debug(f"[TracingService] Langfuse 未启用，跳过追踪: {name}")
            return

        try:
            trace = self._langfuse.trace(name=name, metadata=metadata or {})
            trace.generation(
                name=f"{name}_generation",
                model=model,
                input=input_messages,
                output=output_text,
            )
            logger.debug(f"[TracingService] ✅ LLM 调用已追踪: {name}")
        except Exception as e:
            logger.warning(f"[TracingService] ⚠️ 追踪失败（Fail-Open）: {name}, error={e}")

    def trace_span(
        self,
        name: str,
        input_data: dict[str, Any] | None = None,
        output_data: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        记录通用 Span 追踪
        
        Fail-Open: 如果追踪失败，仅记录日志，不抛出异常
        """
        if not self.enabled or not self._langfuse:
            logger.debug(f"[TracingService] Langfuse 未启用，跳过 Span 追踪: {name}")
            return

        try:
            trace = self._langfuse.trace(name=name, metadata=metadata or {})
            trace.span(
                name=f"{name}_span",
                input=input_data,
                output=output_data,
            )
            logger.debug(f"[TracingService] ✅ Span 已追踪: {name}")
        except Exception as e:
            logger.warning(f"[TracingService] ⚠️ Span 追踪失败（Fail-Open）: {name}, error={e}")

    def flush(self) -> None:
        """
        刷新待发送的追踪数据
        
        Fail-Open: 如果刷新失败，仅记录日志，不抛出异常
        """
        if not self.enabled or not self._langfuse:
            return

        try:
            self._langfuse.flush()
            logger.debug("[TracingService] ✅ Langfuse 数据已刷新")
        except Exception as e:
            logger.warning(f"[TracingService] ⚠️ 刷新失败（Fail-Open）: {e}")

    def shutdown(self) -> None:
        """
        关闭追踪服务
        
        Fail-Open: 如果关闭失败，仅记录日志，不抛出异常
        """
        if not self.enabled or not self._langfuse:
            return

        try:
            self._langfuse.flush()
            logger.info("[TracingService] ✅ Langfuse 已关闭")
        except Exception as e:
            logger.warning(f"[TracingService] ⚠️ 关闭失败（Fail-Open）: {e}")


# 全局单例
_tracing_service: TracingService | None = None


def get_tracing_service() -> TracingService:
    """获取 TracingService 单例"""
    global _tracing_service
    if _tracing_service is None:
        _tracing_service = TracingService()
    return _tracing_service


def shutdown_tracing_service():
    """关闭 TracingService"""
    global _tracing_service
    if _tracing_service:
        _tracing_service.shutdown()
        _tracing_service = None
