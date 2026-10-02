from __future__ import annotations

import asyncio
import time
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from customer_service.intents.policies import validate_tool_for_intent
from customer_service.tools.context import ToolExecutionContext
from customer_service.tools.models import RetryPolicy, ToolResult
from customer_service.tools.errors import ToolError, ToolExecutionError


class ToolSpec(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    allowed_intents: tuple[str, ...]
    side_effect: bool
    timeout_seconds: float
    retry_policy: RetryPolicy = RetryPolicy.NONE
    args_model: type[BaseModel]
    result_model: type[BaseModel] = ToolResult
    handler: Any = Field(exclude=True)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        if spec.name in self._tools:
            logger.error("duplicate tool registered: {}", spec.name)
            raise ValueError(f"duplicate tool registered: {spec.name}")
        self._tools[spec.name] = spec
        logger.info("registered tool: {}", spec.name)

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise KeyError(name)
        return self._tools[name]

    def list_tools(self) -> list[ToolSpec]:
        return list(self._tools.values())

    def names(self) -> set[str]:
        return set(self._tools)


class ToolRuntime:
    def __init__(self, registry: ToolRegistry, max_concurrency: int = 20) -> None:
        self.registry = registry
        self._semaphore = asyncio.Semaphore(max_concurrency)

    async def execute(
        self,
        name: str,
        args: dict[str, Any],
        context: ToolExecutionContext,
    ) -> ToolResult:
        try:
            spec = self.registry.get(name)
        except KeyError:
            logger.warning("tool not found: {}", name)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="TOOL_NOT_FOUND", message=f"tool not found: {name}"),
            )

        # 问题修复2-5: 真正的 allowed_intents 检查
        # 不仅检查是否为空，还要检查当前 intent 是否在允许列表中
        if not spec.allowed_intents:
            logger.error("tool {} has empty allowlist", name)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="TOOL_POLICY_INVALID", message="tool allowlist is empty"),
            )

        # 检查当前 intent 是否在 allowed_intents 中
        intent_value = context.intent.value if context.intent else None
        if intent_value and intent_value not in spec.allowed_intents:
            logger.warning("tool {} denied for intent {}: not in allowed_intents {}", name, intent_value, spec.allowed_intents)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="AUTH_DENIED", message=f"tool not allowed for intent {intent_value}"),
            )

        try:
            parsed_args = spec.args_model.model_validate(args)
        except Exception as exc:
            logger.warning("tool args validation failed: {} {}", name, exc)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="VALIDATION_ERROR", message=str(exc)),
            )

        # 问题修复2-5: 计算剩余时间（基于 request_deadline）
        remaining_time = spec.timeout_seconds
        if hasattr(context, 'request_deadline_monotonic') and context.request_deadline_monotonic:
            current_time = time.monotonic()
            deadline_remaining = context.request_deadline_monotonic - current_time
            if deadline_remaining <= 0:
                logger.warning("tool {} request deadline already exceeded", name)
                return ToolResult(
                    tool_name=name,
                    ok=False,
                    error=ToolError(code="DEADLINE_EXCEEDED", message="request deadline exceeded before tool execution"),
                )
            remaining_time = min(remaining_time, deadline_remaining)

        # 问题修复2-5: 实现有限重试机制
        max_attempts = 2 if spec.retry_policy == RetryPolicy.READ_ONCE_RETRY else 1
        attempt = 0
        last_error = None

        while attempt < max_attempts:
            attempt += 1
            try:
                async with self._semaphore:
                    result = await asyncio.wait_for(
                        spec.handler(parsed_args, context),
                        timeout=remaining_time,
                    )

                # 问题修复2-5: 验证结果结构
                if not isinstance(result, ToolResult):
                    try:
                        result = ToolResult.model_validate(result)
                    except Exception as exc:
                        logger.error("tool result validation failed: {} {}", name, exc)
                        return ToolResult(
                            tool_name=name,
                            ok=False,
                            error=ToolError(code="TOOL_RESULT_INVALID", message=str(exc)),
                        )

                if result.tool_name != name:
                    result.tool_name = name
                result.side_effect = spec.side_effect or result.side_effect

                # 成功执行，返回结果
                if result.ok or attempt >= max_attempts:
                    return result

                # 失败但可以重试
                if result.error and result.error.retryable and attempt < max_attempts:
                    logger.info("tool {} attempt {} failed but retryable, retrying...", name, attempt)
                    last_error = result.error
                    await asyncio.sleep(0.1)  # 短暂退避
                    continue
                else:
                    return result

            except asyncio.TimeoutError:
                logger.error("tool timeout: {} (attempt {}/{})", name, attempt, max_attempts)
                last_error = ToolError(code="TOOL_TIMEOUT", message="tool execution timed out", retryable=True)

                if attempt < max_attempts:
                    logger.info("tool {} timeout, retrying...", name)
                    await asyncio.sleep(0.1)
                    continue
                else:
                    return ToolResult(
                        tool_name=name,
                        ok=False,
                        error=last_error,
                    )

            except ToolExecutionError as exc:
                # 问题修复2-5: 保留精细的错误分类
                logger.warning("tool execution error: {} (attempt {}/{}): {}", name, attempt, max_attempts, exc.error.code)
                last_error = exc.error

                # 只有 retryable 的错误才重试
                if exc.error.retryable and attempt < max_attempts:
                    logger.info("tool {} retryable error, retrying...", name)
                    await asyncio.sleep(0.1)
                    continue
                else:
                    return ToolResult(
                        tool_name=name,
                        ok=False,
                        error=exc.error.dict() if hasattr(exc.error, 'dict') else exc.error,
                    )

            except Exception as exc:
                # 其他未知异常
                logger.exception("tool execution failed: {} (attempt {}/{})", name, attempt, max_attempts)
                last_error = ToolError(code="TOOL_EXECUTION_FAILED", message=f"{type(exc).__name__}: {exc}", retryable=False)

                # 未知异常不重试
                return ToolResult(
                    tool_name=name,
                    ok=False,
                    error=last_error.dict() if hasattr(last_error, 'dict') else last_error,
                )

        # 所有重试都失败了
        return ToolResult(
            tool_name=name,
            ok=False,
            error=(last_error.dict() if hasattr(last_error, 'dict') else last_error) if last_error else ToolError(code="TOOL_EXECUTION_FAILED", message="all attempts failed").dict(),
        )
