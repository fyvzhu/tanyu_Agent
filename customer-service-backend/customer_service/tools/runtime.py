from __future__ import annotations

import asyncio
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field

from customer_service.intents.policies import validate_tool_for_intent
from customer_service.tools.context import ToolExecutionContext
from customer_service.tools.models import RetryPolicy, ToolError, ToolResult


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

        if not spec.allowed_intents:
            logger.error("tool {} has empty allowlist", name)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="TOOL_POLICY_INVALID", message="tool allowlist is empty"),
            )

        if not validate_tool_for_intent(context.intent, name):
            logger.warning("tool {} denied for intent {}", name, context.intent.value)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="AUTH_DENIED", message="tool not allowed for intent"),
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

        try:
            async with self._semaphore:
                result = await asyncio.wait_for(
                    spec.handler(parsed_args, context),
                    timeout=spec.timeout_seconds,
                )
        except TimeoutError:
            logger.error("tool timeout: {}", name)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="TOOL_TIMEOUT", message="tool execution timed out", retryable=True),
            )
        except Exception as exc:
            logger.exception("tool execution failed: {}", name)
            return ToolResult(
                tool_name=name,
                ok=False,
                error=ToolError(code="TOOL_EXECUTION_FAILED", message=f"{type(exc).__name__}: {exc}"),
            )

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
        return result
